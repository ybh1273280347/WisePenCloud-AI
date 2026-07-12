from __future__ import annotations

from typing import Any

from chat.application.tools.core import (
    ToolDefinition,
    ToolConfigSpec,
    ToolExecutionError,
    ToolLLMSpec,
    ToolParametersSchema,
    ToolPolicy,
    ToolRiskLevel,
)
from chat.application.tools.core.tool_return import ToolReturn
from chat.application.tools.search_tools.web_search.core.errors import (
    WebSearchCustomApiKeyInvalid,
    WebSearchCustomApiKeyMissing,
    WebSearchEmptyResult,
    WebSearchError,
    WebSearchInternalError,
    WebSearchNetworkError,
)
from chat.application.tools.search_tools.web_search.factories.search_source_factory import (
    SearchSourceFactory,
)
from chat.application.tools.search_tools.web_search.providers.models import SearchMode, SearchProviderName
from chat.application.tools.search_tools.web_search.result_builder import build_search_tool_return
from chat.application.tools.search_tools.web_search.search_pipeline import SearchPipeline

DEFAULT_SEARCH_RESULTS = 10
MAX_SEARCH_RESULTS = 20
WEB_SEARCH_TOOL_TIMEOUT_SECONDS = 300.0


PARAMETERS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "minLength": 1,
            "description": "Required. A concise, search-engine-friendly query.",
        },
        "mode": {
            "type": "string",
            "enum": [SearchMode.WEB.value, SearchMode.ACADEMIC.value],
            "default": SearchMode.WEB.value,
            "description": "Use academic for literature search; unsupported sources fall back to web.",
        },
        "max_results": {
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_SEARCH_RESULTS,
            "default": DEFAULT_SEARCH_RESULTS,
            "description": "Maximum candidate results per search request.",
        },
    },
    "required": ["query"],
    "additionalProperties": False,
}


class BaseSearchTool:
    """统一搜索工具门面，具体工具只声明名称和 provider。"""

    __slots__ = (
        "_definition",
        "_provider",
        "_search_pipeline",
        "_source_factory",
        "_tool_name",
    )

    def __init__(
            self,
            *,
            tool_name: str,
            provider: SearchProviderName | None,
            search_pipeline: SearchPipeline,
            source_factory: SearchSourceFactory,
    ) -> None:
        self._tool_name = tool_name
        self._provider = provider
        self._search_pipeline = search_pipeline
        self._source_factory = source_factory
        self._definition = ToolDefinition(
            llm_spec=ToolLLMSpec(
                name=tool_name,
                description=_tool_description(provider),
                parameters_schema=ToolParametersSchema(PARAMETERS_SCHEMA),
            ),
            policy=ToolPolicy(
                expose_by_default=True,
                expose_to_ui=True,
                user_toggleable=provider is None,
                persist_output=True,
                risk_level=ToolRiskLevel.LOW,
                timeout_seconds=WEB_SEARCH_TOOL_TIMEOUT_SECONDS,
                cache_chunked=False,
            ),
            config_spec=_config_spec(provider),
        )

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    async def execute(
            self,
            context: dict[str, Any],
            config: dict[str, Any] | None = None,
            **kwargs: Any,
    ) -> ToolReturn:
        query = kwargs["query"].strip()
        mode = SearchMode(str(kwargs.get("mode") or SearchMode.WEB.value))
        max_results = max(1, min(kwargs.get("max_results") or DEFAULT_SEARCH_RESULTS, MAX_SEARCH_RESULTS))

        try:
            api_key = None
            if self._provider is not None:
                api_key = str((config or {}).get("api_key") or "").strip()
                if not api_key:
                    raise WebSearchCustomApiKeyMissing(
                        provider=self._provider,
                        reason="缺少工具配置中的 API key",
                    )

            source = self._source_factory.build(
                provider=self._provider,
                api_key=api_key,
            )
            pipeline_result = await self._search_pipeline.search(
                query=query,
                max_results=max_results,
                source=source,
                mode=mode,
            )
        except WebSearchCustomApiKeyMissing as exc:
            raise self._execution_error("api_key_missing", exc, retryable=False) from exc
        except WebSearchCustomApiKeyInvalid as exc:
            raise self._execution_error("api_key_invalid", exc, retryable=False) from exc
        except WebSearchNetworkError as exc:
            raise self._execution_error("network_error", exc, retryable=True) from exc
        except WebSearchEmptyResult as exc:
            raise self._execution_error("empty_result", exc, retryable=True) from exc
        except WebSearchInternalError as exc:
            raise self._execution_error("unavailable", exc, retryable=False) from exc
        except WebSearchError as exc:
            raise self._execution_error("failed", exc, retryable=False) from exc

        return build_search_tool_return(
            pipeline_result.search_result,
            candidates=pipeline_result.candidates,
            responses=pipeline_result.search_result.responses,
            tool_name=self._tool_name,
            mode=mode.value,
            recommended_ids=pipeline_result.recommended_ids,
        )

    def _execution_error(
            self,
            reason: str,
            exc: Exception,
            *,
            retryable: bool,
    ) -> ToolExecutionError:
        return ToolExecutionError(
            reason=f"{self._tool_name}_{reason}",
            detail_reason=str(exc),
            retryable=retryable,
        )


def _tool_description(provider: SearchProviderName | None) -> str:
    source = "the platform search source" if provider is None else f"the user's configured {provider.value} API key"
    if provider is None:
        academic_rule = "  - Academic mode uses the active source capability and falls back to web when unavailable.\n"
    elif provider.capability.academic:
        academic_rule = "  - This source supports native academic search.\n"
    else:
        academic_rule = "  - Academic mode falls back to web search for this source.\n"
    return (
        f"Search with {source} and return ranked candidates.\n"
        "\n"
        "WHEN TO TRIGGER:\n"
        "  - Use this tool when the user needs external information.\n"
        f"{academic_rule}"
        "EXECUTION RULES:\n"
        "  - Execute exactly one explicit query per tool call.\n"
        "  - If results need evidence, fetch selected candidate URLs with web_fetch.\n"
    )


def _config_spec(provider: SearchProviderName | None) -> ToolConfigSpec | None:
    if provider is None:
        return None
    return ToolConfigSpec(
        schema={
            "type": "object",
            "properties": {
                "api_key": {
                    "type": "string",
                    "title": "API Key",
                    "description": f"API key for {provider.value} search.",
                    "writeOnly": True,
                },
            },
            "additionalProperties": False,
        },
        required_keys=("api_key",),
        secret_keys=("api_key",),
    )
