from __future__ import annotations

from typing import Any

from chat.application.tools.core import (
    ToolDefinition,
    ToolExecutionError,
    ToolLLMSpec,
    ToolParametersSchema,
    ToolPolicy,
    ToolRiskLevel,
)
from chat.application.tools.core.tool_return import ToolReturn
from chat.application.tools.tool_settings import tool_settings
from chat.application.tools.web_tools._search_tool_utils import (
    select_recommended_ids,
    store_candidate_mappings,
)
from chat.application.tools.web_tools.search_services.candidate_store.repository_protocol import (
    WebSearchCandidateRepository,
)
from chat.application.tools.web_tools.search_services.core.errors import (
    WebSearchCustomApiKeyInvalid,
    WebSearchCustomApiKeyMissing,
    WebSearchEmptyResult,
    WebSearchError,
    WebSearchNetworkError,
)
from chat.application.tools.web_tools.search_services.factories.custom_source_factory import (
    WebSearchCustomSourceFactory,
)
from chat.application.tools.web_tools.search_services.factories.platform_source_factory import (
    WebSearchPlatformSourceFactory,
)
from chat.application.tools.web_tools.search_services.core.runtime_context import (
    WebSearchRuntimeConfig,
)
from chat.application.tools.web_tools.search_services.academic_search import AcademicSearchService
from chat.application.tools.web_tools.search_services.result_builders.academic import (
    build_academic_search_tool_return,
)
from chat.application.tools.web_tools.search_services.pipeline.candidates_builder import build_candidates
from chat.application.tools.web_tools.search_services.core.sources import WebSearchSourceKind

DEFAULT_ACADEMIC_SEARCH_RESULTS = tool_settings.WEB_SEARCH_DEFAULT_RESULTS
MAX_ACADEMIC_SEARCH_RESULTS = tool_settings.WEB_SEARCH_MAX_RESULTS
MAX_RECOMMENDED_CANDIDATES = tool_settings.WEB_SEARCH_MAX_RECOMMENDED_CANDIDATES
FALLBACK_CANDIDATES_COUNT = tool_settings.WEB_SEARCH_FALLBACK_CANDIDATES_COUNT

PARAMETERS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "question": {
            "type": "string",
            "minLength": 1,
            "description": (
                "Required. The user's academic information need, in the user's own language."
            ),
        },
        "query": {
            "type": "string",
            "minLength": 1,
            "description": (
                "Required. The academic search query to execute for this tool call. "
                "Write it in paper-style or literature-style wording."
            ),
        },
        "max_results": {
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_ACADEMIC_SEARCH_RESULTS,
            "default": DEFAULT_ACADEMIC_SEARCH_RESULTS,
            "description": "Maximum candidate results per academic search request.",
        },
    },
    "required": ["question", "query"],
    "additionalProperties": False,
}


class AcademicSearchTool:
    __slots__ = (
        "_candidate_repository",
        "_candidate_ttl_seconds",
        "_custom_source_factory",
        "_definition",
        "_platform_source_factory",
        "_service",
    )

    def __init__(
            self,
            *,
            service: AcademicSearchService,
            custom_source_factory: WebSearchCustomSourceFactory,
            platform_source_factory: WebSearchPlatformSourceFactory,
            candidate_repository: WebSearchCandidateRepository,
            candidate_ttl_seconds: int = 3600,
    ) -> None:
        self._service = service
        self._custom_source_factory = custom_source_factory
        self._platform_source_factory = platform_source_factory
        self._candidate_repository = candidate_repository
        self._candidate_ttl_seconds = candidate_ttl_seconds
        self._definition = ToolDefinition(
            llm_spec=ToolLLMSpec(
                name="academic_search",
                description=(
                    "Search academic web results with the active academic-capable source and return explicit paper candidates.\n"
                    "\n"
                    "WHEN TO TRIGGER:\n"
                    "  - MUST trigger when the user explicitly wants papers, citations, literature, venues, or research evidence.\n"
                    "  - SHOULD trigger when the user needs paper candidates before fetching full text.\n"
                    "DO NOT TRIGGER when:\n"
                    "  - The user needs general web pages or news coverage — use web_search instead.\n"
                    "  - The user already has a concrete paper DOI or title and only needs lightweight metadata enrichment.\n"
                    "\n"
                    "EXECUTION RULES:\n"
                    "  - Execute exactly one explicit query per tool call.\n"
                    "  - If the query returns no results, stop and report failure; rewrite the query yourself before calling academic_search again.\n"
                    "  - The tool may optionally hydrate search results with OpenAlex if the user configured an OpenAlex key.\n"
                    "  - The tool uses a small internal model only to rank returned candidates.\n"
                    "\n"
                    "OUTPUT RULES:\n"
                    "  - Fetch selected search refs before using them as evidence.\n"
                ),
                parameters_schema=ToolParametersSchema(PARAMETERS_SCHEMA),
            ),
            policy=ToolPolicy(
                expose_by_default=False,
                persist_output=True,
                risk_level=ToolRiskLevel.LOW,
                timeout_seconds=tool_settings.WEB_SEARCH_TOOL_TIMEOUT_SECONDS,
                cache_chunked=False,
                required_context_keys=("user_id", "session_id", "search_config"),
            ),
        )

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    async def execute(self, context: dict[str, Any], **kwargs: Any) -> ToolReturn:
        question = kwargs["question"].strip()
        query = kwargs["query"].strip()
        max_results = kwargs.get("max_results") or DEFAULT_ACADEMIC_SEARCH_RESULTS
        search_config: WebSearchRuntimeConfig = context["search_config"]

        if (
                search_config.provider is None
                or not search_config.provider.supports_academic_search
                or not search_config.supports_academic
        ):
            raise ToolExecutionError(
                reason="academic_search_unavailable",
                detail_reason="academic_search requires an active academic-capable search source.",
                retryable=False,
            )

        try:
            if search_config.source_kind == WebSearchSourceKind.CUSTOM:
                if not search_config.is_valid:
                    raise WebSearchCustomApiKeyInvalid(
                        provider=search_config.provider,
                        reason=search_config.error_message or "custom 搜索配置不可用",
                    )
                source = self._custom_source_factory.build(search_config)
            else:
                source = self._platform_source_factory.build(search_config)

            # 执行单次学术查询；空结果交给模型改写 query 后重新调用。
            result = await self._service.search(
                query=query,
                max_results=max(1, min(max_results, MAX_ACADEMIC_SEARCH_RESULTS)),
                source=source,
            )
            base_candidates = build_candidates(result.responses, search_config=search_config)
            if not base_candidates:
                raise WebSearchEmptyResult(
                    provider=search_config.provider,
                    reason="学术搜索没有返回结果",
                )
            # 使用 OpenAlex 对候选结果进行水合（补充 DOI、引用数、作者、开放获取信息）
            outcomes = await self._service.hydrate_candidates(
                candidates=base_candidates,
                openalex_api_key=search_config.openalex_api_key,
            )
            final_candidates = tuple(outcome.candidate for outcome in outcomes)
            await store_candidate_mappings(
                repository=self._candidate_repository,
                ttl_seconds=self._candidate_ttl_seconds,
                user_id=str(context["user_id"]),
                candidates=final_candidates,
            )
        except WebSearchCustomApiKeyMissing as exc:
            raise ToolExecutionError(
                reason="academic_search_api_key_missing",
                detail_reason=str(exc),
                retryable=False,
            ) from exc
        except WebSearchCustomApiKeyInvalid as exc:
            raise ToolExecutionError(
                reason="academic_search_api_key_invalid",
                detail_reason=str(exc),
                retryable=False,
            ) from exc
        except WebSearchNetworkError as exc:
            # Exa / OpenAlex 网络不可达
            raise ToolExecutionError(
                reason="academic_search_network_error",
                detail_reason=str(exc),
                retryable=True,
            ) from exc
        except WebSearchEmptyResult as exc:
            # 搜索无结果，非故障，可重试
            raise ToolExecutionError(
                reason="academic_search_empty_result",
                detail_reason=str(exc),
                retryable=True,
            ) from exc
        except WebSearchError as exc:
            # 其他不确定错误，不重试
            raise ToolExecutionError(
                reason="academic_search_failed",
                detail_reason=str(exc),
                retryable=False,
            ) from exc

        recommended_ids = await select_recommended_ids(
            search_query=query,
            candidates=final_candidates,
            max_recommended_candidates=MAX_RECOMMENDED_CANDIDATES,
            fallback_candidates_count=FALLBACK_CANDIDATES_COUNT,
        )
        return build_academic_search_tool_return(
            query=query,
            outcomes=outcomes,
            recommended_ids=recommended_ids,
        )
