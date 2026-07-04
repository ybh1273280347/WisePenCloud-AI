from __future__ import annotations

from chat.application.tools.common.web_content_cache import (
    WebContentCacheAdapter,
    WebContentCacheEntryRepository,
    WebContentCacheSourceRecord,
    WebContentCacheValueRepository,
)
from chat.application.tools.common.web_content_cache.refresh_queue import (
    WEB_FETCH_REFRESH_JOB,
    WebContentCacheRefreshTaskPublisher,
)
from common.logger import info
from .models import RawFetchOutput, WebFetchResult

_PRODUCER_NAME = "web_fetch"
_REFRESH_LOCK_TTL_SECONDS = 300


class WebFetchCacheAdapter:
    """web_fetch 对 URL 内容缓存的窄适配层。"""

    __slots__ = ("_cleaner_name", "_content_cache_adapter")

    def __init__(
            self,
            *,
            cleaner_name: str,
            entry_repository: WebContentCacheEntryRepository | None = None,
            value_repository: WebContentCacheValueRepository | None = None,
            refresh_task_publisher: WebContentCacheRefreshTaskPublisher | None = None,
    ) -> None:
        self._cleaner_name = cleaner_name
        self._content_cache_adapter = WebContentCacheAdapter(
            entry_repository=entry_repository,
            value_repository=value_repository,
            refresh_task_publisher=refresh_task_publisher,
        )

    async def read_result(
            self,
            *,
            url: str,
            user_id: str,
            session_id: str,
    ) -> WebFetchResult | None:
        cached = await self._content_cache_adapter.read_markdown_page(
            url=url,
            user_id=user_id,
            session_id=session_id,
            refresh_job_prefix=_PRODUCER_NAME,
            refresh_task_name=WEB_FETCH_REFRESH_JOB,
            refresh_lock_ttl_seconds=_REFRESH_LOCK_TTL_SECONDS,
        )
        if cached is None:
            return None

        info(
            "网页抓取命中缓存",
            url=url,
            cache_mode=cached.cache_mode.value,
            stale=cached.stale,
        )
        return WebFetchResult(
            source_url=cached.source_url,
            final_url=cached.final_url,
            status_code=cached.status_code,
            content_type=cached.content_type,
            title=cached.title,
            markdown=cached.markdown,
        )

    async def write_html_result(
            self,
            *,
            url: str,
            user_id: str,
            source_scope: str,
            raw: RawFetchOutput,
            result: WebFetchResult,
    ) -> None:
        await self._content_cache_adapter.write_html_markdown(
            url=url,
            user_id=user_id,
            source_scope=source_scope,
            record=_source_record(raw),
            markdown=result.markdown,
            title=result.title,
            cleaner=self._cleaner_name,
            producer=_PRODUCER_NAME,
        )

    async def write_non_html_stub(
            self,
            *,
            user_id: str,
            source_scope: str,
            raw: RawFetchOutput,
    ) -> str | None:
        return await self._content_cache_adapter.write_non_html_stub(
            user_id=user_id,
            source_scope=source_scope,
            record=_source_record(raw),
        )


def _source_record(raw: RawFetchOutput) -> WebContentCacheSourceRecord:
    return WebContentCacheSourceRecord(
        source_url=raw.source_url,
        final_url=raw.final_url,
        status_code=raw.status_code,
        content_type=raw.content_type,
        headers=raw.headers,
        fetcher=raw.fetcher,
        file_label=raw.file_label,
        raw_html=raw.raw_html,
    )
