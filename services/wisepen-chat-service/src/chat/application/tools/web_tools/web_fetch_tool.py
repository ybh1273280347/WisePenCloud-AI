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
from chat.application.tools.utils.url import UrlSecurityError, validate_public_http_url
from chat.application.tools.web_tools.fetch_services import FetchCoordinator
from chat.application.tools.web_tools.fetch_services.core.errors import UrlFetchError
from common.logger import warn

# --- 全局常量定义 ---
MAX_URLS = 64

PARAMETERS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "urls": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "minItems": 1,
            "maxItems": MAX_URLS,
            "description": (
                "Target URLs to fetch. Each MUST be a full http(s) URL. "
                "Large sets are handled by an internal scheduler."
            ),
        },
    },
    "required": ["urls"],
    "additionalProperties": False,
}


class WebFetchTool:
    """Web fetch 工具门面，批量抓取 URL。

    复用 FetchCoordinator 的 httpx -> scrapling fallback 链路 + 清洗 + 质量判断。
    HTML 页面返回清洗后的 markdown；非 HTML 文件移交 ToolRunFileStore 返回 tfile_* 引用。
    单个 URL 失败不阻塞其他，转为 failed 项。

    与 web_crawl 的区别：
    - web_fetch 抓取一批独立 URL，URL 之间无关联
    - web_crawl 从种子 URL 出发递归爬取，自动发现并跟进链接
    """

    __slots__ = ("_definition", "_service")

    def __init__(
            self,
            *,
            service: FetchCoordinator,
    ) -> None:
        self._service = service

        self._definition = ToolDefinition(
            llm_spec=ToolLLMSpec(
                name="web_fetch",
                description=(
                    "Fetch one or more URLs in parallel and return cleaned markdown (HTML) or file references (non-HTML).\n"
                    "\n"
                    "WHEN TO TRIGGER:\n"
                    "  - MUST trigger when the user provides specific URL(s) and wants their content.\n"
                    "  - SHOULD trigger when search results surface concrete URLs that need to be read.\n"
                    "  - SHOULD trigger for normal HTML pages or when you are unsure whether a URL is HTML or a file.\n"
                    "DO NOT TRIGGER when:\n"
                    "  - The user only needs search candidates — use platform_search or a provider search tool instead.\n"
                    "  - Multiple related pages on the same site are needed — use web_crawl instead.\n"
                    "  - The target is an obvious direct document file URL (PDF/Office/spreadsheet/etc.) and the user needs document content — call document_parse with direct_urls instead.\n"
                    "  - The URL is already fetched in this session — reuse the cached result instead of re-fetching.\n"
                    "\n"
                    "INPUT RULES:\n"
                    "  - Provide urls to fetch full http(s) URLs directly.\n"
                    "  - Large sets are handled by an internal scheduler with separate fast and fallback resource pools.\n"
                    "\n"
                    "OUTPUT RULES:\n"
                    "  - HTML page: returns title and cleaned markdown.\n"
                    "  - Non-HTML file: returns file_ref (tfile_*) and file_label; pass file_ref to document_parse to extract content.\n"
                    "  - Avoid producing this file_ref handoff when the original user input was already an obvious direct file URL; document_parse can parse those URLs directly.\n"
                    "  - Per-URL failure is returned in the failed list with a reason; do NOT silently drop failed URLs.\n"
                    "  - Within one session, do NOT re-fetch the same url unless new information is required.\n"
                ),
                parameters_schema=ToolParametersSchema(PARAMETERS_SCHEMA),
            ),
            policy=ToolPolicy(
                expose_by_default=True,
                persist_output=True,
                risk_level=ToolRiskLevel.MEDIUM,
                timeout_seconds=tool_settings.WEB_FETCH_TOOL_TIMEOUT_SECONDS,
                cache_chunked=True,
                required_context_keys=("user_id", "session_id"),
            ),
        )

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    async def execute(self, context: dict[str, Any], **kwargs: Any) -> ToolReturn:
        urls: list[str] = []
        source_scope = "web_public"

        for u in kwargs["urls"]:
            url = u.strip()
            try:
                urls.append(validate_public_http_url(url))
            except UrlSecurityError as exc:
                raise ToolExecutionError(
                    reason="invalid_url",
                    detail_reason=str(exc),
                    retryable=False,
                ) from exc

        # 2. 调用批量异步核心抓取服务
        user_id = str(context["user_id"])
        session_id = str(context["session_id"])

        try:
            batch = await self._service.fetch_many(
                urls,
                user_id=user_id,
                session_id=session_id,
                source_scope=source_scope,
            )
        except UrlFetchError as exc:
            raise ToolExecutionError(
                reason="web_fetch_failed",
                detail_reason=str(exc),
                retryable=True,
            ) from exc
        except Exception as exc:
            warn(
                "web fetch unexpected error.",
                e=exc,
                urls=tuple(urls),
                source_scope=source_scope,
                audit_message="web_fetch 批量抓取发生未预期异常，已包装为不可重试 ToolExecutionError。",
            )
            raise ToolExecutionError(
                reason="web_fetch_unexpected_error",
                detail_reason=str(exc),
                retryable=False,
            ) from exc

        cacheable_texts = tuple(r.markdown for r in batch.items if r.markdown)

        # visible_result 中只保留模型可直接消费的来源和下游定位符，正文走 cacheable_texts。
        visible_items = []
        for r in batch.items:
            item: dict[str, object] = {"source_url": r.source_url}
            if r.title:
                item["title"] = r.title
            if r.file_ref:
                item["file_ref"] = r.file_ref
            if r.file_label:
                item["file_label"] = r.file_label
            if r.warnings:
                item["warnings"] = r.warnings
            visible_items.append(item)

        visible_result: dict[str, object] = {
            "items": tuple(visible_items),
            "failed": batch.failed,
        }
        if batch.warnings:
            visible_result["warnings"] = batch.warnings

        return ToolReturn(
            tag="web_fetch_result",
            visible_result=visible_result,
            cacheable_texts=cacheable_texts,
        )
