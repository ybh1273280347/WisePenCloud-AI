from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from lxml import html as lxml_html

from chat.application.tools.common.web_content_cache import WebContentCacheRepository
from common.logger import info, warn
from ._utils import judge_quality
from .cleaners import BaseCleaner
from .core.errors import UrlFetchError, UrlFetchUnsupportedUrlError
from .core.models import WebFetchResult
from .fetchers import WebFetcher
from .infra.cache import WebFetchCache


@dataclass(frozen=True, slots=True)
class _CrawlPage:
    result: WebFetchResult
    raw_html: str | None


@dataclass(frozen=True, slots=True)
class WebCrawlResult:
    pages: tuple[WebFetchResult, ...]
    timed_out: bool = False


class WebCrawler:
    """复用 static → stealthy 抓取链路，按 BFS 递归爬取 HTML 页面。"""

    __slots__ = (
        "_static_fetcher",
        "_stealthy_fetcher",
        "_cleaner",
        "_cache",
        "_min_text_length",
        "_concurrency",
    )

    def __init__(
            self,
            *,
            static_fetcher: WebFetcher,
            stealthy_fetcher: WebFetcher,
            cleaner: BaseCleaner,
            content_cache_repository: WebContentCacheRepository | None = None,
            min_text_length: int = 200,
            concurrency: int = 16,
    ) -> None:
        self._static_fetcher = static_fetcher
        self._stealthy_fetcher = stealthy_fetcher
        self._cleaner = cleaner
        self._cache = WebFetchCache(
            cleaner_name=cleaner.name,
            repository=content_cache_repository,
            producer_name="web_crawl",
        )
        self._min_text_length = min_text_length
        self._concurrency = concurrency

    async def crawl(
            self,
            seed_url: str,
            *,
            user_id: str,
            source_scope: str = "web_public",
            max_pages: int = 100,
            max_depth: int = 3,
            same_domain: bool = True,
    ) -> WebCrawlResult:
        """按 BFS 递归爬取 seed_url。"""
        base_domain = urlparse(seed_url).netloc
        queue: deque[tuple[str, int]] = deque([(seed_url, 0)])
        discovered = {seed_url}
        results: list[WebFetchResult] = []

        try:
            while queue and len(results) < max_pages:
                batch = [
                    queue.popleft()
                    for _ in range(
                        min(
                            len(queue),
                            self._concurrency,
                            max_pages - len(results),
                        )
                    )
                ]

                pages = await asyncio.gather(
                    *(
                        self._fetch_one(
                            url,
                            user_id=user_id,
                            source_scope=source_scope,
                        )
                        for url, _ in batch
                    ),
                    return_exceptions=True,
                )

                for (url, depth), page in zip(batch, pages, strict=True):
                    if isinstance(page, Exception):
                        warn("web_crawl fetch failed", url=url, reason=str(page))
                        continue

                    if page is None:
                        continue

                    results.append(page.result)
                    if (
                            depth >= max_depth
                            or len(results) >= max_pages
                            or page.raw_html is None
                    ):
                        continue

                    for child_url in _extract_links(
                            page.raw_html,
                            base_url=url,
                            base_domain=base_domain,
                            same_domain=same_domain,
                    ):
                        if child_url in discovered:
                            continue
                        discovered.add(child_url)
                        queue.append((child_url, depth + 1))

        except asyncio.CancelledError:
            return WebCrawlResult(pages=tuple(results), timed_out=True)

        return WebCrawlResult(pages=tuple(results))

    async def _fetch_one(
            self,
            url: str,
            *,
            user_id: str,
            source_scope: str,
    ) -> _CrawlPage | None:
        cached = await self._cache.read_page(url=url, user_id=user_id)
        if cached is not None:
            return _CrawlPage(
                result=cached.result,
                raw_html=cached.raw_html,
            )

        used_stealthy = False

        try:
            raw = await self._static_fetcher.fetch(url)
        except UrlFetchUnsupportedUrlError as exc:
            warn(
                "web_crawl skip unsupported url result",
                url=url,
                reason=exc.reason,
            )
            return None
        except UrlFetchError as exc:
            warn(
                "web_crawl static failed, fallback to stealthy",
                url=url,
                reason=exc.reason,
            )
            used_stealthy = True

            try:
                raw = await self._stealthy_fetcher.fetch(url)
            except UrlFetchError as fallback_exc:
                warn(
                    "web_crawl stealthy failed",
                    url=url,
                    reason=fallback_exc.reason,
                )
                return None

        if raw.raw_html is None:
            info("web_crawl skip non-html", url=url, label=raw.file_label)
            return None

        cleaned = self._cleaner.clean(raw.raw_html, url=raw.source_url)
        quality = judge_quality(
            raw=raw,
            cleaned=cleaned,
            min_text_length=self._min_text_length,
        )

        if not used_stealthy and quality.should_fallback:
            warn(
                "web_crawl static quality insufficient, fallback to stealthy",
                url=url,
                reason=quality.reason,
            )

            try:
                fallback = await self._stealthy_fetcher.fetch(url)
            except UrlFetchError as exc:
                warn(
                    "web_crawl stealthy failed, using static result",
                    url=url,
                    reason=exc.reason,
                )
            else:
                if fallback.raw_html is not None:
                    raw = fallback
                    cleaned = self._cleaner.clean(
                        raw.raw_html,
                        url=raw.source_url,
                    )
                    quality = judge_quality(
                        raw=raw,
                        cleaned=cleaned,
                        min_text_length=self._min_text_length,
                    )

        result = WebFetchResult(
            source_url=raw.source_url,
            status_code=raw.status_code,
            content_type=raw.content_type,
            title=cleaned.title,
            markdown=cleaned.markdown,
        )

        if not quality.should_fallback:
            await self._cache.write_html_result(
                url=url,
                user_id=user_id,
                source_scope=source_scope,
                raw=raw,
                result=result,
            )

        return _CrawlPage(result=result, raw_html=raw.raw_html)


def _extract_links(
        raw_html: str,
        *,
        base_url: str,
        base_domain: str,
        same_domain: bool,
) -> list[str]:
    """提取并去重页面中的 HTTP(S) 链接。"""
    try:
        hrefs = lxml_html.fromstring(raw_html).xpath("//a/@href")
    except Exception:
        return []

    links: list[str] = []
    seen: set[str] = set()

    for href in hrefs:
        href = href.split("#", 1)[0].strip()
        if not href:
            continue

        try:
            absolute = urljoin(base_url, href)
            parsed = urlparse(absolute)
        except ValueError:
            continue

        if parsed.scheme not in {"http", "https"}:
            continue
        if same_domain and parsed.netloc != base_domain:
            continue
        if absolute in seen:
            continue

        seen.add(absolute)
        links.append(absolute)

    return links