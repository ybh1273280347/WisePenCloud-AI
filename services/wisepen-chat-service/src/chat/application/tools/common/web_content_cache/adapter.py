from __future__ import annotations

from dataclasses import dataclass

from .models import WebContentCacheMode
from .refresh_queue import WebContentCacheRefreshTaskPublisher
from .repository import WebContentCacheEntryRepository, WebContentCacheValueRepository
from .service import (
    CachedMarkdownPage,
    HtmlCacheWrite,
    NonHtmlCacheStubWrite,
    WebContentCacheService,
)


@dataclass(frozen=True, slots=True)
class WebContentCacheSourceRecord:
    source_url: str
    final_url: str | None
    status_code: int | None
    content_type: str | None
    headers: dict[str, str]
    fetcher: str | None
    file_label: str | None = None
    raw_html: str | None = None


class WebContentCacheAdapter:
    """工具侧对 WebContentCacheService 的适配层。"""

    __slots__ = ("_service",)

    def __init__(
            self,
            *,
            entry_repository: WebContentCacheEntryRepository | None = None,
            value_repository: WebContentCacheValueRepository | None = None,
            refresh_task_publisher: WebContentCacheRefreshTaskPublisher | None = None,
    ) -> None:
        self._service = WebContentCacheService(
            entry_repository=entry_repository,
            value_repository=value_repository,
            refresh_task_publisher=refresh_task_publisher,
        )

    async def read_markdown_page(
            self,
            *,
            url: str,
            user_id: str,
            session_id: str,
            refresh_job_prefix: str,
            refresh_task_name: str,
            refresh_lock_ttl_seconds: int,
    ) -> CachedMarkdownPage | None:
        return await self._service.read_markdown_page(
            url=url,
            user_id=user_id,
            session_id=session_id,
            refresh_job_prefix=refresh_job_prefix,
            refresh_task_name=refresh_task_name,
            refresh_lock_ttl_seconds=refresh_lock_ttl_seconds,
        )

    async def write_html_markdown(
            self,
            *,
            url: str,
            user_id: str,
            source_scope: str,
            record: WebContentCacheSourceRecord,
            markdown: str | None,
            title: str | None,
            cleaner: str | None,
            producer: str,
    ) -> str | None:
        if not markdown:
            return None

        return await self._service.write_html_markdown(
            HtmlCacheWrite(
                url=url,
                user_id=user_id,
                source_scope=source_scope,
                final_url=record.final_url,
                status_code=record.status_code,
                content_type=record.content_type,
                raw_html=record.raw_html,
                markdown=markdown,
                title=title,
                headers=record.headers,
                fetcher=record.fetcher,
                cleaner=cleaner,
                producer=producer,
            )
        )

    async def write_non_html_stub(
            self,
            *,
            user_id: str,
            source_scope: str,
            record: WebContentCacheSourceRecord,
    ) -> str | None:
        return await self._service.write_non_html_stub(
            NonHtmlCacheStubWrite(
                user_id=user_id,
                source_scope=source_scope,
                source_url=record.source_url,
                final_url=record.final_url,
                status_code=record.status_code,
                content_type=record.content_type,
                headers=record.headers,
                fetcher=record.fetcher,
                file_label=record.file_label,
            )
        )

    async def read_markdown_by_metadata(
            self,
            *,
            user_id: str,
            metadata: dict[str, object],
            parser_version: str | None = None,
    ) -> CachedMarkdownPage | None:
        return await self._service.read_markdown_by_metadata(
            user_id=user_id,
            metadata=metadata,
            parser_version=parser_version,
        )

    async def write_markdown_from_metadata(
            self,
            *,
            user_id: str,
            metadata: dict[str, object],
            content_type: str | None,
            markdown: str,
            parser: str,
            parser_version: str,
    ) -> str | None:
        return await self._service.write_markdown_from_metadata(
            user_id=user_id,
            metadata=metadata,
            content_type=content_type,
            markdown=markdown,
            parser=parser,
            parser_version=parser_version,
        )

    async def schedule_stale_refresh(
            self,
            *,
            url: str,
            user_id: str,
            session_id: str,
            source_scope: str,
            cache_mode: WebContentCacheMode,
            refresh_job_prefix: str,
            payload: dict[str, object] | None = None,
            refresh_identity_suffix: str | None = None,
            refresh_task_name: str,
            refresh_lock_ttl_seconds: int,
    ) -> None:
        await self._service.schedule_stale_refresh(
            url=url,
            user_id=user_id,
            session_id=session_id,
            source_scope=source_scope,
            cache_mode=cache_mode,
            refresh_job_prefix=refresh_job_prefix,
            payload=payload,
            refresh_identity_suffix=refresh_identity_suffix,
            refresh_task_name=refresh_task_name,
            refresh_lock_ttl_seconds=refresh_lock_ttl_seconds,
        )
