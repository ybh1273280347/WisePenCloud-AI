from __future__ import annotations

import asyncio
from dataclasses import dataclass

from chat.application.tools.common.tool_run_file_store import ToolRunFileStore
from chat.application.tools.common.web_content_cache import (
    NonHtmlCacheStubWrite,
    WebContentCacheMode,
    WebContentCacheService,
)
from chat.application.tools.common.web_content_cache import (
    WebContentCacheEntryRepository,
    WebContentCacheValueRepository,
)
from chat.application.tools.common.web_content_cache.refresh_queue import (
    DOCUMENT_PARSE_REFRESH_JOB,
    WebContentCacheRefreshTaskPublisher,
)
from chat.application.tools.document_tools.document_parse.models import DocumentParseRequest
from chat.application.tools.document_tools.document_parse.service import DocumentParseService
from chat.application.tools.tool_settings import tool_settings
from chat.application.tools.utils.url import FetchedUrl
from common.logger import warn

_DOCUMENT_PARSE_CACHE_PARSER_VERSION = "document_parse:v1"
_REFRESH_LOCK_TTL_SECONDS = tool_settings.DOCUMENT_PARSE_REFRESH_LOCK_TTL_SECONDS


@dataclass(frozen=True, slots=True)
class ParsedCacheHit:
    markdown: str
    cache_mode: WebContentCacheMode
    stale: bool


class DocumentParseCache:
    __slots__ = ("_content_cache_service", "_file_store", "_parse_service")

    def __init__(
            self,
            *,
            file_store: ToolRunFileStore,
            parse_service: DocumentParseService,
            content_cache_entry_repository: WebContentCacheEntryRepository | None = None,
            content_cache_value_repository: WebContentCacheValueRepository | None = None,
            refresh_task_publisher: WebContentCacheRefreshTaskPublisher | None = None,
    ) -> None:
        self._file_store = file_store
        self._parse_service = parse_service
        self._content_cache_service = WebContentCacheService(
            entry_repository=content_cache_entry_repository,
            value_repository=content_cache_value_repository,
            refresh_task_publisher=refresh_task_publisher,
        )

    async def write_direct_url_cache_stub(
            self,
            *,
            user_id: str,
            raw: FetchedUrl,
    ) -> str | None:
        return await self._content_cache_service.write_non_html_stub(
            NonHtmlCacheStubWrite(
                user_id=user_id,
                source_scope="web_public",
                source_url=raw.source_url,
                final_url=raw.final_url,
                status_code=raw.status_code,
                content_type=raw.content_type,
                headers=raw.headers,
                fetcher=raw.fetcher,
                file_label=raw.file_label,
            )
        )

    async def read_parsed_web_cache(
            self,
            *,
            user_id: str,
            metadata: dict[str, object],
    ) -> ParsedCacheHit | None:
        cached = await self._content_cache_service.read_markdown_by_metadata(
            user_id=user_id,
            metadata=metadata,
            parser_version=_DOCUMENT_PARSE_CACHE_PARSER_VERSION,
        )
        if cached is None:
            return None

        return ParsedCacheHit(
            markdown=cached.markdown,
            cache_mode=cached.cache_mode,
            stale=cached.stale,
        )

    async def schedule_stale_parse_refresh(
            self,
            *,
            user_id: str,
            session_id: str,
            file_ref: str,
            metadata: dict[str, object],
            cache_mode: WebContentCacheMode,
    ) -> None:
        source_url = string_metadata(metadata, "source_url")
        source_scope = source_scope_from_metadata(metadata)
        if source_url is None or source_scope is None:
            return

        try:
            await self._content_cache_service.schedule_stale_refresh(
                url=source_url,
                user_id=user_id,
                session_id=session_id,
                source_scope=source_scope,
                cache_mode=cache_mode,
                refresh_job_prefix="document_parse",
                payload={
                    "user_id": user_id,
                    "session_id": session_id,
                    "file_ref": file_ref,
                    "cache_mode": cache_mode.value,
                },
                refresh_identity_suffix=_DOCUMENT_PARSE_CACHE_PARSER_VERSION,
                refresh_task_name=DOCUMENT_PARSE_REFRESH_JOB,
                refresh_lock_ttl_seconds=_REFRESH_LOCK_TTL_SECONDS,
            )
        except Exception:
            warn(
                "文档解析刷新任务调度失败，降级为本进程后台任务",
                file_ref=file_ref,
                source_url=source_url,
                cache_mode=cache_mode,
                audit_message="文档解析 stale 缓存刷新任务调度失败，已尝试使用本进程后台任务兜底。",
            )
            asyncio.create_task(
                self.refresh_stale_parse_cache(
                    user_id=user_id,
                    session_id=session_id,
                    file_ref=file_ref,
                )
            )

    async def refresh_stale_parse_cache(
            self,
            *,
            user_id: str,
            session_id: str,
            file_ref: str,
    ) -> None:
        try:
            resolved = await self._file_store.resolve_ref(
                user_id=user_id,
                session_id=session_id,
                ref_id=file_ref,
            )
            result = await self._parse_service.parse(
                DocumentParseRequest(
                    file_path=resolved.path,
                    original_filename=resolved.filename,
                    mime_type=resolved.content_type,
                    source_scope=source_scope_from_metadata(resolved.metadata),
                    source_kind=string_metadata(resolved.metadata, "source_kind"),
                )
            )
            markdown = result.markdown.strip()
            if markdown:
                await self.write_parsed_web_cache(
                    user_id=user_id,
                    metadata=resolved.metadata,
                    content_type=resolved.content_type,
                    markdown=markdown,
                )
        except Exception:
            warn(
                "文档解析 stale 后台刷新失败",
                file_ref=file_ref,
                audit_message="文档解析后台刷新失败，已保留调用方收到的旧缓存结果。",
            )

    async def write_parsed_web_cache(
            self,
            *,
            user_id: str,
            metadata: dict[str, object],
            content_type: str | None,
            markdown: str,
    ) -> None:
        source_url = string_metadata(metadata, "source_url")
        source_scope = source_scope_from_metadata(metadata)
        if source_url is None or source_scope is None:
            return

        try:
            await self._content_cache_service.write_markdown_from_metadata(
                user_id=user_id,
                metadata=metadata,
                content_type=content_type,
                markdown=markdown,
                parser="document_parse",
                parser_version=_DOCUMENT_PARSE_CACHE_PARSER_VERSION,
            )
        except Exception:
            warn(
                "文档解析缓存写入失败",
                source_url=source_url,
                source_scope=source_scope,
                audit_message="文档解析结果写入网页内容缓存失败，不影响本次解析结果返回。",
            )


def source_scope_from_metadata(metadata: dict[str, object]) -> str | None:
    value = metadata.get("source_scope")
    return str(value) if isinstance(value, str) and value else None


def string_metadata(metadata: dict[str, object], key: str) -> str | None:
    value = metadata.get(key)
    return str(value) if isinstance(value, str) and value else None


def direct_url_metadata(
        *,
        url: str,
        final_url: str | None,
        content_type: str | None,
        cache_doc_id: str | None = None,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "source_kind": "web_fetch",
        "source_scope": "web_public",
        "source_url": url,
        "final_url": final_url,
        "content_type": content_type,
    }
    if cache_doc_id:
        metadata["source_cache_doc_id"] = cache_doc_id
    return metadata
