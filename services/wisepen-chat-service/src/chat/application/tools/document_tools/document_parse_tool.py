from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from chat.application.tools.common.tool_run_file_store import ToolRunFileStore
from chat.application.tools.common.tool_run_file_store.errors import tool_file_error_reason
from chat.application.tools.common.web_content_cache import (
    WebContentCacheEntryRepository,
    WebContentCacheValueRepository,
)
from chat.application.tools.common.web_content_cache.refresh_queue import (
    WebContentCacheRefreshTaskPublisher,
)
from chat.application.tools.core import (
    ToolDefinition,
    ToolExactlyOneOf,
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
from chat.application.tools.utils.url import (
    FetchedUrl,
    UrlFetcherError,
    UrlFetcherUnsupportedUrlError,
    UrlSecurityError,
    fetch_url,
    filename_from_url,
    validate_public_http_url,
)

MAX_DOCUMENT_PARSE_FILE_REFS = 64
SERVICE_BATCH_SIZE = tool_settings.DOCUMENT_PARSE_MAX_FILE_REFS
DOCUMENT_PARSE_CONCURRENCY = tool_settings.DOCUMENT_PARSE_CONCURRENCY


@dataclass(frozen=True, slots=True)
class DocumentParseToolItem:
    source: str  # 调用方传入的 tfile_* 引用或直链 URL
    status: str  # success 或 failed
    file_name: str | None = None  # 解析出的展示文件名
    reason: str | None = None  # 单项失败原因，供模型判断下一步


class DocumentParseTool:
    """批量解析 tfile_* 文档引用的工具入口。"""

    __slots__ = (
        "_cache",
        "_content_cache_entry_repository",
        "_content_cache_value_repository",
        "_definition",
        "_file_store",
        "_max_download_bytes",
        "_parse_service",
        "_refresh_task_publisher",
        "_url_download_http_client",
    )

    def __init__(
            self,
            *,
            file_store: ToolRunFileStore,
            parse_service: DocumentParseService,
            content_cache_entry_repository: WebContentCacheEntryRepository | None = None,
            content_cache_value_repository: WebContentCacheValueRepository | None = None,
            refresh_task_publisher: WebContentCacheRefreshTaskPublisher | None = None,
            url_download_http_client: httpx.AsyncClient | None = None,
            max_download_bytes: int = 52_428_800,
    ) -> None:
        self._file_store = file_store
        self._parse_service = parse_service
        self._content_cache_entry_repository = content_cache_entry_repository
        self._content_cache_value_repository = content_cache_value_repository
        self._refresh_task_publisher = refresh_task_publisher
        self._url_download_http_client = url_download_http_client
        self._max_download_bytes = max_download_bytes
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
                    "  - MUST trigger directly when the user provides obvious document file URLs (PDF, Office, spreadsheet, or similar non-HTML files) and asks for their content.\n"
                    "  - SHOULD trigger when the user asks to read, summarize, or answer questions about an attached document.\n"
                    "DO NOT TRIGGER when:\n"
                    "  - You need to read normal HTML pages — use web_fetch or web_crawl instead.\n"
                    "  - You already have content_ids from a previous parse — use tool_content_read or tool_content_sequential_read instead.\n"
                    "  - You need OCR for a standalone image after inspecting it — use image_ocr instead.\n"
                    "\n"
                    "INPUT RULES:\n"
                    "  - Provide file_refs for tfile_* values returned by web_fetch or another previous tool.\n"
                    "  - Provide direct_urls for full http(s) direct document file URLs.\n"
                    "  - Provide exactly one of file_refs or direct_urls; never provide both.\n"
                    "  - Pass all selected files in one array; the tool auto-batches large sets and parses files concurrently within each batch.\n"
                    "  - Do not wrap obvious direct document file URLs through web_fetch first; pass direct_urls directly.\n"
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
                            "file_refs": {
                                "type": "array",
                                "items": {
                                    "type": "string",
                                    "minLength": 1,
                                },
                                "minItems": 1,
                                "maxItems": MAX_DOCUMENT_PARSE_FILE_REFS,
                                "description": (
                                    "tfile_* references produced by previous tools. "
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
                                    "Full http(s) direct document file URLs. "
                                    "Large sets are automatically split into internal batches. "
                                    "Use this for obvious non-HTML file links instead of calling web_fetch first."
                                ),
                            },
                        },
                        "additionalProperties": False,
                    },
                    exactly_one_of=(
                        ToolExactlyOneOf(
                            groups=(("file_refs",), ("direct_urls",)),
                            message="Provide exactly one of file_refs or direct_urls.",
                        ),
                    ),
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

    async def refresh_stale_parse_cache(
            self,
            *,
            user_id: str,
            session_id: str,
            file_ref: str,
    ) -> None:
        await self._cache.refresh_stale_parse_cache(
            user_id=user_id,
            session_id=session_id,
            file_ref=file_ref,
        )

    async def execute(self, context: dict[str, Any], **kwargs: Any) -> ToolReturn:
        """批量解析文件引用，单项失败不影响其它文件。"""
        user_id = str(context["user_id"])
        session_id = str(context["session_id"])
        file_refs = tuple(str(value).strip() for value in kwargs.get("file_refs", ()))
        direct_urls = tuple(str(value).strip() for value in kwargs.get("direct_urls", ()))

        if file_refs:
            item_results = await self._parse_file_ref_batches(
                user_id=user_id,
                session_id=session_id,
                file_refs=file_refs,
            )
        else:
            item_results = await self._parse_direct_url_batches(
                user_id=user_id,
                session_id=session_id,
                direct_urls=direct_urls,
            )

        cacheable_texts: list[str] = []
        items: list[DocumentParseToolItem] = []
        for item, markdown in item_results:
            if markdown:
                item = DocumentParseToolItem(
                    source=item.source,
                    status=item.status,
                    file_name=item.file_name,
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
                            source=file_ref,
                            status="success",
                            file_name=resolved.filename,
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
                        source=file_ref,
                        status="success",
                        file_name=resolved.filename,
                    ),
                    markdown or None,
                )
            except Exception as e:
                return (
                    DocumentParseToolItem(
                        source=file_ref,
                        status="failed",
                        reason=tool_file_error_reason(e, default="parse_failed"),
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
        if self._url_download_http_client is None:
            return (
                DocumentParseToolItem(
                    source=direct_url,
                    status="failed",
                    reason="direct_url_fetch_unavailable",
                ),
                None,
            )

        url = direct_url.strip()
        try:
            url = validate_public_http_url(url)
        except UrlSecurityError as e:
            return (
                DocumentParseToolItem(
                    source=direct_url,
                    status="failed",
                    reason=f"invalid_direct_url:{e}",
                ),
                None,
            )

        raw: FetchedUrl | None = None
        try:
            metadata = direct_url_metadata(url=url, final_url=url, content_type=None)
            cache_hit = await self._cache.read_parsed_web_cache(
                user_id=user_id,
                metadata=metadata,
            )
            if cache_hit is not None:
                return (
                    DocumentParseToolItem(
                        source=direct_url,
                        status="success",
                        file_name=filename_from_url(url),
                    ),
                    cache_hit.markdown,
                )

            raw = await fetch_url(
                url,
                http_client=self._url_download_http_client,
                max_response_bytes=self._max_download_bytes,
                allow_html=False,
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
        except UrlFetcherUnsupportedUrlError as e:
            reason = (
                "direct_url_not_file"
                if e.reason == "url_resolved_to_html"
                else f"direct_url_fetch_failed:{e.reason}"
            )
            return (
                DocumentParseToolItem(
                    source=direct_url,
                    status="failed",
                    reason=reason,
                ),
                None,
            )
        except UrlFetcherError as e:
            return (
                DocumentParseToolItem(
                    source=direct_url,
                    status="failed",
                    reason=f"direct_url_fetch_failed:{e.reason}",
                ),
                None,
            )
        except Exception:
            return (
                DocumentParseToolItem(
                    source=direct_url,
                    status="failed",
                    reason="direct_url_parse_failed",
                ),
                None,
            )
        finally:
            if raw is not None and raw.file_path is not None:
                with contextlib.suppress(OSError):
                    Path(raw.file_path).unlink(missing_ok=True)
