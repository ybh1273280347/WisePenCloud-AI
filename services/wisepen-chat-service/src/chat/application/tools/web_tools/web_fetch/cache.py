from __future__ import annotations

from dataclasses import dataclass

from chat.application.tools.common.web_content_cache import (
    HtmlCacheWrite,
    NonHtmlCacheStubWrite,
    WebContentCacheEntryRepository,
    WebContentCacheService,
    WebContentCacheValueRepository,
)
from common.logger import info
from .models import RawFetchOutput, WebFetchResult

_PRODUCER_NAME = "web_fetch"


@dataclass(frozen=True, slots=True)
class CachedWebFetchPage:
    """命中 URL 缓存的网页结果，保留 crawl 抽链需要的 raw_html。"""

    result: WebFetchResult
    raw_html: str | None


class WebFetchCache:
    """网页抓取工具族的 URL 内容缓存边界。"""

    __slots__ = ("_cleaner_name", "_content_cache_service", "_producer_name")

    def __init__(
            self,
            *,
            cleaner_name: str,
            entry_repository: WebContentCacheEntryRepository | None = None,
            value_repository: WebContentCacheValueRepository | None = None,
            producer_name: str = _PRODUCER_NAME,
    ) -> None:
        self._cleaner_name = cleaner_name
        self._producer_name = producer_name
        self._content_cache_service = WebContentCacheService(
            entry_repository=entry_repository,
            value_repository=value_repository,
        )

    async def read_result(
            self,
            *,
            url: str,
            user_id: str,
    ) -> WebFetchResult | None:
        cached = await self.read_page(url=url, user_id=user_id)
        if cached is None:
            return None

        return cached.result

    async def read_page(
            self,
            *,
            url: str,
            user_id: str,
    ) -> CachedWebFetchPage | None:
        cached = await self._content_cache_service.read_markdown_page(
            url=url,
            user_id=user_id,
        )
        if cached is None:
            return None

        info(
            "网页抓取命中缓存",
            url=url,
            cache_mode=cached.cache_mode.value,
        )
        return CachedWebFetchPage(
            result=WebFetchResult(
                source_url=cached.source_url,
                final_url=cached.final_url,
                status_code=cached.status_code,
                content_type=cached.content_type,
                title=cached.title,
                markdown=cached.markdown,
            ),
            raw_html=cached.raw_html,
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
        await self._content_cache_service.write_html_markdown(
            HtmlCacheWrite(
                url=url,
                user_id=user_id,
                source_scope=source_scope,
                final_url=raw.final_url,
                status_code=raw.status_code,
                content_type=raw.content_type,
                raw_html=raw.raw_html,
                markdown=result.markdown,
                title=result.title,
                headers=raw.headers,
                fetcher=raw.fetcher,
                cleaner=self._cleaner_name,
                producer=self._producer_name,
            )
        )

    async def write_non_html_stub(
            self,
            *,
            user_id: str,
            source_scope: str,
            raw: RawFetchOutput,
    ) -> str | None:
        return await self._content_cache_service.write_non_html_stub(
            NonHtmlCacheStubWrite(
                user_id=user_id,
                source_scope=source_scope,
                source_url=raw.source_url,
                final_url=raw.final_url,
                status_code=raw.status_code,
                content_type=raw.content_type,
                headers=raw.headers,
                fetcher=raw.fetcher,
                file_label=raw.file_label,
            )
        )
