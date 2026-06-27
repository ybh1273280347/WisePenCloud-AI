from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from chat.application.tools.common.tool_run_file_store import ToolRunFileStore
from chat.application.tools.common.tool_run_file_store.errors import (
    InvalidToolFileRefError,
    ToolFileNotFoundError,
    ToolFileUnreadableError,
)
from chat.application.tools.core import (
    ToolDefinition,
    ToolExecutionError,
    ToolLLMSpec,
    ToolParametersSchema,
    ToolPolicy,
    ToolRiskLevel,
)
from chat.application.tools.core.tool_return import (
    SuggestedAction,
    SuggestedActionPriority,
    ToolReturn,
)
from chat.application.tools.document_tools.document_parse.cache import (
    DocumentParseCache,
    direct_url_metadata,
    source_scope_from_metadata,
    string_metadata,
)
from chat.application.tools.document_tools.document_parse.models import DocumentParseRequest
from chat.application.tools.document_tools.document_parse.service import DocumentParseService
from chat.application.tools.tool_settings import tool_settings
from chat.application.tools.utils.batching import batched
from chat.application.tools.common.web_content_cache.refresh_queue import (
    WebContentCacheRefreshTaskPublisher,
)
from chat.application.tools.common.web_content_cache import (
    WebContentCacheEntryRepository,
    WebContentCacheValueRepository,
)
from chat.application.tools.web_tools.web_fetch.errors import WebFetchError
from chat.application.tools.web_tools.web_fetch.fetchers.base import BaseFetcher, RawFetchOutput
from chat.application.tools.web_tools.web_fetch.utils import filename_from_url

MAX_DOCUMENT_PARSE_FILE_REFS = 64
SERVICE_BATCH_SIZE = tool_settings.DOCUMENT_PARSE_MAX_FILE_REFS
DOCUMENT_PARSE_CONCURRENCY = tool_settings.DOCUMENT_PARSE_CONCURRENCY


@dataclass(frozen=True, slots=True)
class DocumentParseToolItem:
    file_ref: str  # 调用方传入的 tfile_* 引用
    status: str  # success 或 failed
    file_name: str | None = None  # 解析出的展示文件名
    content_ref: int | None = None  # 对应 ToolReturn.cacheable_texts 的索引
    source_scope: str | None = None  # 通过 ToolRunFileStore metadata 识别出的来源范围
    reason: str | None = None  # 单项失败原因，供模型判断下一步


class DocumentParseTool:
    """批量解析 tfile_* 文档引用的工具入口。"""

    __slots__ = (
        "_cache",
        "_content_cache_entry_repository",
        "_content_cache_value_repository",
        "_definition",
        "_direct_fetcher",
        "_file_store",
        "_parse_service",
        "_refresh_task_publisher",
    )

    def __init__(
        self,
        *,
        file_store: ToolRunFileStore,
        parse_service: DocumentParseService,
        content_cache_entry_repository: WebContentCacheEntryRepository | None = None,
        content_cache_value_repository: WebContentCacheValueRepository | None = None,
        refresh_task_publisher: WebContentCacheRefreshTaskPublisher | None = None,
        direct_fetcher: BaseFetcher | None = None,
    ) -> None:
        self._file_store = file_store
        self._parse_service = parse_service
        self._content_cache_entry_repository = content_cache_entry_repository
        self._content_cache_value_repository = content_cache_value_repository
        self._refresh_task_publisher = refresh_task_publisher
        self._direct_fetcher = direct_fetcher
        self._cache = DocumentParseCache(
            file_store=file_store,
            parse_service=parse_service,
            content_cache_entry_repository=content_cache_entry_repository,
            content_cache_value_repository=content_cache_value_repository,
            refresh_task_publisher=refresh_task_publisher,
        )
        self._definition = ToolDefinition(
            llm_spec=ToolLLMSpec(
                name="document_parse",
                description=(
                    "Parse temporary document files or direct file URLs into Markdown.\n"
                    "\n"
                    "WHEN TO TRIGGER:\n"
                    "  - MUST trigger when previous tools returned tfile_* references (e.g. from web_fetch, web_crawl, or uploads) and you need their textual content.\n"
                    "  - MUST trigger directly when the user provides obvious file URLs (PDF, image, Office, spreadsheet, or similar non-HTML files) and asks for their content.\n"
                    "  - SHOULD trigger when the user asks to read, summarize, or answer questions about an attached document.\n"
                    "DO NOT TRIGGER when:\n"
                    "  - You need to read normal HTML pages — use web_fetch or web_crawl instead.\n"
                    "  - You already have content_ids from a previous parse — use tool_content_read or tool_content_sequential_read instead.\n"
                    "  - You only have a non-file web page URL; mode='from_direct_urls' is only for direct file URLs.\n"
                    "\n"
                    "INPUT RULES:\n"
                    "  - mode='from_web_fetch' => provide file_refs with tfile_* values returned by web_fetch or another previous tool.\n"
                    "  - mode='from_direct_urls' => provide direct_urls with full http(s) file URLs.\n"
                    "  - file_refs and direct_urls are mutually exclusive; never provide both.\n"
                    "  - Pass all selected files in one array; the tool auto-batches large sets and parses files concurrently within each batch.\n"
                    "  - Do not wrap obvious direct file URLs through web_fetch first; use mode='from_direct_urls' directly.\n"
                    "\n"
                    "OUTPUT RULES:\n"
                    "  - Returns one item per input file with status success or failed.\n"
                    "  - Each successfully parsed file produces a cacheable content unit; failed files return a reason code.\n"
                    "  - Use the suggested tool_content_read action to locate answer-relevant windows in the parsed Markdown."
                ),
                parameters_schema=ToolParametersSchema(
                    {
                        "type": "object",
                        "properties": {
                            "mode": {
                                "type": "string",
                                "enum": ["from_web_fetch", "from_direct_urls"],
                                "description": (
                                    "Required. Use from_web_fetch for tfile_* file_refs; "
                                    "use from_direct_urls for obvious direct file URLs."
                                ),
                            },
                            "file_refs": {
                                "type": "array",
                                "items": {
                                    "type": "string",
                                    "minLength": 1,
                                },
                                "minItems": 1,
                                "maxItems": MAX_DOCUMENT_PARSE_FILE_REFS,
                                "description": (
                                    "Required when mode='from_web_fetch'. tfile_* references produced by previous tools. "
                                    "Large sets are automatically split into internal batches."
                                ),
                            },
                            "direct_urls": {
                                "type": "array",
                                "items": {
                                    "type": "string",
                                    "minLength": 1,
                                },
                                "minItems": 1,
                                "maxItems": MAX_DOCUMENT_PARSE_FILE_REFS,
                                "description": (
                                    "Required when mode='from_direct_urls'. Full http(s) direct file URLs. "
                                    "Large sets are automatically split into internal batches. "
                                    "Use this for obvious non-HTML file links instead of calling web_fetch first."
                                ),
                            },
                        },
                        "required": ["mode"],
                        "additionalProperties": False,
                    }
                ),
            ),
            policy=ToolPolicy(
                expose_by_default=True,
                persist_output=True,
                risk_level=ToolRiskLevel.LOW,
                required_context_keys=("user_id", "session_id"),
                timeout_seconds=tool_settings.DOCUMENT_PARSE_TOOL_TIMEOUT_SECONDS,
                cache_chunked=True,
            ),
        )

    @property
    def definition(self) -> ToolDefinition:
        """返回工具元定义。"""
        return self._definition

    async def execute(self, context: dict[str, Any], **kwargs: Any) -> ToolReturn:
        """批量解析文件引用，单项失败不影响其它文件。"""
        user_id = str(context["user_id"])
        session_id = str(context["session_id"])
        mode = str(kwargs["mode"])
        file_refs = tuple(str(value) for value in kwargs.get("file_refs", ()))
        direct_urls = tuple(str(value) for value in kwargs.get("direct_urls", ()))

        match mode:
            case "from_web_fetch":
                if not file_refs:
                    raise ToolExecutionError(
                        reason="missing_file_refs",
                        detail_reason="file_refs is required when mode='from_web_fetch'.",
                        retryable=False,
                    )
                if direct_urls:
                    raise ToolExecutionError(
                        reason="mixed_document_parse_inputs",
                        detail_reason="direct_urls must not be provided when mode='from_web_fetch'.",
                        retryable=False,
                    )
                item_results = await self._parse_file_ref_batches(
                    user_id=user_id,
                    session_id=session_id,
                    file_refs=file_refs,
                )
            case "from_direct_urls":
                if not direct_urls:
                    raise ToolExecutionError(
                        reason="missing_direct_urls",
                        detail_reason="direct_urls is required when mode='from_direct_urls'.",
                        retryable=False,
                    )
                if file_refs:
                    raise ToolExecutionError(
                        reason="mixed_document_parse_inputs",
                        detail_reason="file_refs must not be provided when mode='from_direct_urls'.",
                        retryable=False,
                    )
                item_results = await self._parse_direct_url_batches(
                    user_id=user_id,
                    session_id=session_id,
                    direct_urls=direct_urls,
                )
            case _:
                raise ToolExecutionError(
                    reason="invalid_mode",
                    detail_reason="mode must be 'from_web_fetch' or 'from_direct_urls'.",
                    retryable=False,
                )

        cacheable_texts: list[str] = []
        items: list[DocumentParseToolItem] = []
        for item, markdown in item_results:
            if markdown:
                item = DocumentParseToolItem(
                    file_ref=item.file_ref,
                    status=item.status,
                    file_name=item.file_name,
                    content_ref=len(cacheable_texts),
                    source_scope=item.source_scope,
                )
                cacheable_texts.append(markdown)
            items.append(item)

        return ToolReturn(
            tag="document_parse_result",
            visible_result={
                "items": tuple(items),
                "suggested_action": SuggestedAction(
                    tool_name="tool_content_read",
                    mode="ranked_expand",
                    reason="Search the parsed Markdown content for answer-relevant windows.",
                    priority=SuggestedActionPriority.HIGH,
                ),
            },
            cacheable_texts=tuple(cacheable_texts),
        )

    async def _parse_file_ref_batches(
        self,
        *,
        user_id: str,
        session_id: str,
        file_refs: tuple[str, ...],
    ) -> list[tuple[DocumentParseToolItem, str | None]]:
        semaphore = asyncio.Semaphore(DOCUMENT_PARSE_CONCURRENCY)
        results: list[tuple[DocumentParseToolItem, str | None]] = []
        for batch_file_refs in batched(file_refs, batch_size=max(1, int(SERVICE_BATCH_SIZE))):
            parse_inputs = [
                self._parse_one(
                    semaphore=semaphore,
                    user_id=user_id,
                    session_id=session_id,
                    file_ref=file_ref,
                )
                for file_ref in batch_file_refs
            ]
            results.extend(await asyncio.gather(*parse_inputs, return_exceptions=False))
        return results

    async def _parse_direct_url_batches(
        self,
        *,
        user_id: str,
        session_id: str,
        direct_urls: tuple[str, ...],
    ) -> list[tuple[DocumentParseToolItem, str | None]]:
        semaphore = asyncio.Semaphore(DOCUMENT_PARSE_CONCURRENCY)
        results: list[tuple[DocumentParseToolItem, str | None]] = []
        for batch_direct_urls in batched(direct_urls, batch_size=max(1, int(SERVICE_BATCH_SIZE))):
            parse_inputs = [
                self._parse_direct_url(
                    semaphore=semaphore,
                    user_id=user_id,
                    session_id=session_id,
                    direct_url=direct_url,
                )
                for direct_url in batch_direct_urls
            ]
            results.extend(await asyncio.gather(*parse_inputs, return_exceptions=False))
        return results

    async def _parse_one(
        self,
        *,
        semaphore: asyncio.Semaphore,
        user_id: str,
        session_id: str,
        file_ref: str,
    ) -> tuple[DocumentParseToolItem, str | None]:
        """解析单个文件引用；异常转换为单项失败。"""
        async with semaphore:
            try:
                resolved = await self._file_store.resolve_ref(
                    user_id=user_id,
                    session_id=session_id,
                    ref_id=file_ref,
                )
                source_scope = source_scope_from_metadata(resolved.metadata)
                source_kind = string_metadata(resolved.metadata, "source_kind")
                cache_hit = await self._cache.read_parsed_web_cache(
                    user_id=user_id,
                    metadata=resolved.metadata,
                )
                if cache_hit is not None:
                    if cache_hit.stale:
                        await self._cache.schedule_stale_parse_refresh(
                            user_id=user_id,
                            session_id=session_id,
                            file_ref=file_ref,
                            metadata=resolved.metadata,
                            cache_mode=cache_hit.cache_mode,
                        )
                    return (
                        DocumentParseToolItem(
                            file_ref=file_ref,
                            status="success",
                            file_name=resolved.filename,
                            source_scope=source_scope,
                        ),
                        cache_hit.markdown,
                    )

                result = await self._parse_service.parse(
                    DocumentParseRequest(
                        file_path=resolved.path,
                        original_filename=resolved.filename,
                        mime_type=resolved.content_type,
                        source_scope=source_scope,
                        source_kind=source_kind,
                    )
                )
                markdown = result.markdown.strip()
                if markdown:
                    await self._cache.write_parsed_web_cache(
                        user_id=user_id,
                        metadata=resolved.metadata,
                        content_type=resolved.content_type,
                        markdown=markdown,
                    )
                return (
                    DocumentParseToolItem(
                        file_ref=file_ref,
                        status="success",
                        file_name=resolved.filename,
                        source_scope=source_scope,
                    ),
                    markdown or None,
                )
            except Exception as e:
                return (
                    DocumentParseToolItem(
                        file_ref=file_ref,
                        status="failed",
                        source_scope=None,
                        reason=_failure_reason(e),
                    ),
                    None,
                )

    async def _parse_direct_url(
        self,
        *,
        semaphore: asyncio.Semaphore,
        user_id: str,
        session_id: str,
        direct_url: str,
    ) -> tuple[DocumentParseToolItem, str | None]:
        """下载明显文件直链并复用 tfile 解析链路。"""
        if self._direct_fetcher is None:
            return (
                DocumentParseToolItem(
                    file_ref=direct_url,
                    status="failed",
                    reason="direct_url_fetch_unavailable",
                ),
                None,
            )

        url = direct_url.strip()
        if not url.startswith(("http://", "https://")):
            return (
                DocumentParseToolItem(
                    file_ref=direct_url,
                    status="failed",
                    reason="invalid_direct_url",
                ),
                None,
            )

        raw: RawFetchOutput | None = None
        try:
            metadata = direct_url_metadata(url=url, final_url=url, content_type=None)
            cache_hit = await self._cache.read_parsed_web_cache(
                user_id=user_id,
                metadata=metadata,
            )
            if cache_hit is not None:
                return (
                    DocumentParseToolItem(
                        file_ref=direct_url,
                        status="success",
                        file_name=filename_from_url(url),
                        source_scope="web_public",
                    ),
                    cache_hit.markdown,
                )

            raw = await self._direct_fetcher.fetch(url)
            if raw.file_path is None:
                return (
                    DocumentParseToolItem(
                        file_ref=direct_url,
                        status="failed",
                        reason="direct_url_not_file",
                    ),
                    None,
                )

            cache_doc_id = await self._cache.write_direct_url_cache_stub(
                user_id=user_id,
                raw=raw,
            )
            metadata = direct_url_metadata(
                url=raw.source_url,
                final_url=raw.final_url or raw.source_url,
                content_type=raw.content_type,
                cache_doc_id=cache_doc_id,
            )
            record = await self._file_store.publish_file(
                user_id=user_id,
                session_id=session_id,
                producer="document_parse",
                path=raw.file_path,
                filename=filename_from_url(raw.final_url or raw.source_url)
                or f"download.{raw.file_label or 'bin'}",
                content_type=raw.content_type,
                ref_prefix="web_public",
                metadata=metadata,
            )
            return await self._parse_one(
                semaphore=semaphore,
                user_id=user_id,
                session_id=session_id,
                file_ref=record.ref_id,
            )
        except WebFetchError as e:
            return (
                DocumentParseToolItem(
                    file_ref=direct_url,
                    status="failed",
                    reason=f"direct_url_fetch_failed:{e.reason}",
                ),
                None,
            )
        except Exception:
            return (
                DocumentParseToolItem(
                    file_ref=direct_url,
                    status="failed",
                    reason="direct_url_parse_failed",
                ),
                None,
            )
        finally:
            if raw is not None and raw.file_path is not None:
                with contextlib.suppress(OSError):
                    Path(raw.file_path).unlink(missing_ok=True)


def _failure_reason(error: Exception) -> str:
    if isinstance(error, InvalidToolFileRefError):
        return "invalid_file_ref"
    if isinstance(error, ToolFileNotFoundError):
        return "file_ref_unavailable"
    if isinstance(error, ToolFileUnreadableError):
        return "file_unreadable"
    return "parse_failed"
