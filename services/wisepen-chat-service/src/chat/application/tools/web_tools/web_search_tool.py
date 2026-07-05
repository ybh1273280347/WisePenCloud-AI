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
from chat.application.tools.web_tools.search_services.candidate_store.repository import (
    WebSearchCandidateRepository,
)
from chat.application.tools.web_tools.search_services.factories.custom_source_factory import (
    WebSearchCustomSourceFactory,
)
from chat.application.tools.web_tools.search_services.errors import (
    WebSearchCustomApiKeyInvalid,
    WebSearchCustomApiKeyMissing,
    WebSearchEmptyResult,
    WebSearchError,
    WebSearchNetworkError,
)
from chat.application.tools.web_tools.search_services.factories.platform_source_factory import (
    WebSearchPlatformSourceFactory,
)
from chat.application.tools.web_tools.search_services.sources import WebSearchSourceKind
from chat.application.tools.web_tools.search_services.services.candidates_builder import build_candidates
from chat.application.tools.web_tools.search_services.services.web_search.result_builder import (
    build_web_search_tool_return,
)
from chat.application.tools.web_tools.search_services.services.web_search.service import WebSearchService

# 边界控制常量（全部通过 tool_settings 调参控制）
DEFAULT_WEB_SEARCH_RESULTS = tool_settings.WEB_SEARCH_DEFAULT_RESULTS
MAX_WEB_SEARCH_RESULTS = tool_settings.WEB_SEARCH_MAX_RESULTS
MAX_RECOMMENDED_CANDIDATES = tool_settings.WEB_SEARCH_MAX_RECOMMENDED_CANDIDATES
FALLBACK_CANDIDATES_COUNT = tool_settings.WEB_SEARCH_FALLBACK_CANDIDATES_COUNT

WEB_SEARCH_TOOL_DESCRIPTION = """\
Search the web for candidate pages and return ranked candidates.

WHEN TO TRIGGER:
  - MUST trigger when the user needs real-time or external information not present in context.
  - SHOULD trigger for fact-checking or verifying claims against external sources.
  - SHOULD trigger when the user explicitly asks to search or browse the web.
DO NOT TRIGGER when:
  - The answer is already available in the conversation context or attached knowledge base.
  - The question is pure common knowledge with no time-sensitivity and the user does not request a source.

EXECUTION RULES:
  - Execute exactly one explicit query per tool call.
  - If the query returns no results, stop and report failure; rewrite the query yourself before calling web_search again.
  - The tool may use a small internal model only to rank returned candidates. It does not rewrite queries or choose provider routes.

INPUT RULES:
  - query MUST be a concise, search-engine-friendly phrasing.
  - Do NOT pass question text verbatim when a shorter search query is clearer.

BEFORE CALLING, ASK YOURSELF:
  - Is query the most direct general-web phrasing for the target fact?
  - If the user clearly wants papers, citations, or research results, use academic_search instead of trying to route that intent through web_search.

COMPLEX QUERY STRATEGY:
  - Fan-out: separate web_search calls in parallel when the user asks for independent facets.
  - Drill-down: make one web_search call, read what comes back, then decide the next explicit search call yourself.
  - Cross-validation: use multiple explicit calls with different source angles or languages when the same fact needs cross-checking.

OUTPUT RULES:
  - supplier_answers and candidate summaries are retrieval hints. If they fully answer the user's question, you may answer without web_fetch; fetch selected URLs when you need stronger evidence, details, or verification.
  - recommended_ids is a priority hint, not a guarantee of correctness; fetch when the answer needs verification beyond summaries.
  - If web_search fails (network/quota/empty), inform the user; do NOT silently answer from parametric memory.
  - Within one session, do NOT re-issue web_search for the same question unless new information is required.
"""

# 大模型 Function Calling 参数契约（保持英文描述以确保模型理解的精确度）
PARAMETERS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "question": {
            "type": "string",
            "minLength": 1,
            "description": (
                "Required. The user's original information need, in the user's own language. "
                "MUST be a non-empty string. Do NOT paraphrase into a search query here; "
                "use query for the search phrasing."
            ),
        },
        "query": {
            "type": "string",
            "minLength": 1,
            "description": (
                "Required. The search query to execute for this tool call. "
                "MUST be a concise, search-engine-friendly phrasing. "
                "Invalid: passing the raw `question` verbatim; passing a full natural-language sentence. "
                "Example: question='苹果最新财报利润' -> query='Apple Q4 2025 earnings net profit'."
            ),
        },
        "max_results": {
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_WEB_SEARCH_RESULTS,
            "default": DEFAULT_WEB_SEARCH_RESULTS,
            "description": "Maximum candidate results per search request. SHOULD be left at default unless the user needs breadth.",
        },
    },
    "required": ["question", "query"],
    "additionalProperties": False,
}


class WebSearchTool:
    """Web 搜索工具门面：单次显式查询。"""

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
            service: WebSearchService,
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
                name="web_search",
                description=WEB_SEARCH_TOOL_DESCRIPTION,
                parameters_schema=ToolParametersSchema(PARAMETERS_SCHEMA),
            ),
            policy=ToolPolicy(
                expose_by_default=True,
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
        max_results = kwargs.get("max_results") or DEFAULT_WEB_SEARCH_RESULTS

        search_config = context["search_config"]

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

            # 2. 执行单次显式查询；空结果交给模型改写 query 后重新调用。
            result = await self._service.search(
                query=query,
                max_results=max(1, min(max_results, MAX_WEB_SEARCH_RESULTS)),
                source=source,
            )
            candidates = build_candidates(result.responses, search_config=search_config)
            if not candidates:
                raise WebSearchEmptyResult(
                    provider=search_config.provider,
                    reason="搜索没有返回结果",
                )

            # 3. 持久化 search_ref → URL 映射，供后续 web_fetch 溯源使用
            await store_candidate_mappings(
                repository=self._candidate_repository,
                ttl_seconds=self._candidate_ttl_seconds,
                user_id=str(context["user_id"]),
                candidates=candidates,
            )

        # 搜索层异常 → 工具层异常：分层隔离，不向外泄漏内部异常类型
        except WebSearchCustomApiKeyMissing as exc:
            # 凭证完全缺失（未配置），不可重试
            raise ToolExecutionError(
                reason="web_search_api_key_missing",
                detail_reason=str(exc),
                retryable=False,
            ) from exc

        except WebSearchCustomApiKeyInvalid as exc:
            # 凭证存在但不可用（如 Key 格式错误），不可重试
            raise ToolExecutionError(
                reason="web_search_api_key_invalid",
                detail_reason=str(exc),
                retryable=False,
            ) from exc

        except WebSearchNetworkError as exc:
            # 网络层面错误（超时/断连），可重试
            raise ToolExecutionError(
                reason="web_search_network_error",
                detail_reason=str(exc),
                retryable=True,
            ) from exc

        except WebSearchEmptyResult as exc:
            # 单次查询无结果，非系统故障；模型可改写 query 后重试。
            raise ToolExecutionError(
                reason="web_search_empty_result",
                detail_reason=str(exc),
                retryable=True,
            ) from exc

        except WebSearchError as exc:
            # 其他不确定的搜索错误，不重试以免无限循环
            raise ToolExecutionError(
                reason="web_search_failed",
                detail_reason=str(exc),
                retryable=False,
            ) from exc

        # 4. 用小模型排序候选结果，选出最相关的推荐给大模型优先关注
        recommended_ids = await select_recommended_ids(
            search_query=query,
            candidates=candidates,
            max_recommended_candidates=MAX_RECOMMENDED_CANDIDATES,
            fallback_candidates_count=FALLBACK_CANDIDATES_COUNT,
        )

        return build_web_search_tool_return(
            result,
            candidates=candidates,
            responses=result.responses,
            display_query=question,
            recommended_ids=recommended_ids,
        )
