from __future__ import annotations

import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SERVICE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SERVICE_ROOT / "src"))
sys.path.insert(0, str(SERVICE_ROOT.parent / "wisepen-common" / "src"))
WEB_TOOLS_ROOT = SERVICE_ROOT / "src" / "chat" / "application" / "tools" / "web_tools"

logger_module = types.ModuleType("common.logger")
logger_module.warn = lambda *args, **kwargs: None
logger_module.info = lambda *args, **kwargs: None
logger_module.error = lambda *args, **kwargs: None
sys.modules["common.logger"] = logger_module

web_tools_module = types.ModuleType("chat.application.tools.web_tools")
web_tools_module.__path__ = [str(WEB_TOOLS_ROOT)]
sys.modules["chat.application.tools.web_tools"] = web_tools_module

web_fetch_module = types.ModuleType("chat.application.tools.web_tools.fetch_services")
web_fetch_module.__path__ = [str(WEB_TOOLS_ROOT / "fetch_services")]
web_fetch_module.FetchCoordinator = object
sys.modules["chat.application.tools.web_tools.fetch_services"] = web_fetch_module

utils_module = types.ModuleType("chat.application.tools.web_tools.fetch_services._utils")
utils_module.judge_quality = lambda **kwargs: types.SimpleNamespace(
    should_fallback=False,
    reason="ok",
)
sys.modules["chat.application.tools.web_tools.fetch_services._utils"] = utils_module

cleaners_module = types.ModuleType("chat.application.tools.web_tools.fetch_services.cleaners")
cleaners_module.BaseCleaner = object
sys.modules["chat.application.tools.web_tools.fetch_services.cleaners"] = cleaners_module

fetchers_module = types.ModuleType("chat.application.tools.web_tools.fetch_services.fetchers")
fetchers_module.WebFetcher = object
sys.modules["chat.application.tools.web_tools.fetch_services.fetchers"] = fetchers_module

from chat.application.tools.common.web_content_cache import (  # noqa: E402
    WebContentCacheMode,
    WebContentCacheValue,
)
from chat.application.tools.web_tools.fetch_services.web_crawl import WebCrawler  # noqa: E402


class _UnusedFetcher:
    def __init__(self) -> None:
        self.calls = 0

    async def fetch(self, url: str) -> object:
        self.calls += 1
        raise AssertionError(f"cache hit should avoid fetching {url}")


class _UnusedCleaner:
    name = "fake_cleaner"

    def clean(self, *_: object, **__: object) -> object:
        raise AssertionError("cache hit should avoid cleaning")


class _CacheRepository:
    def __init__(self, values: dict[tuple[str, str, WebContentCacheMode], WebContentCacheValue]) -> None:
        self._values = values

    async def get_value(
            self,
            *,
            user_id: str,
            url: str,
            cache_mode: WebContentCacheMode | str,
    ) -> WebContentCacheValue | None:
        return self._values.get((user_id, url, WebContentCacheMode(cache_mode)))

    async def set_value(self, value: WebContentCacheValue) -> None:
        raise AssertionError(f"cache hit should avoid writing {value.canonical_url}")

    async def delete_value(
            self,
            *,
            user_id: str,
            url: str,
            cache_mode: WebContentCacheMode | str,
    ) -> None:
        raise AssertionError(f"cache hit should avoid deleting {url}")


@pytest.mark.asyncio
async def test_web_crawler_reuses_fetch_cache_and_cached_raw_html_for_links() -> None:
    user_id = "u1"
    seed_url = "https://example.test/start"
    child_url = "https://example.test/child"

    values = {
        (user_id, seed_url, WebContentCacheMode.PUBLIC): _cache_value(
            user_id=user_id,
            url=seed_url,
            raw_html='<html><body><a href="/child">Child</a></body></html>',
            markdown="# Seed",
            title="Seed",
        ),
        (user_id, child_url, WebContentCacheMode.PUBLIC): _cache_value(
            user_id=user_id,
            url=child_url,
            raw_html="<html><body>Child</body></html>",
            markdown="# Child",
            title="Child",
        ),
    }
    httpx_fetcher = _UnusedFetcher()
    scrapling_fetcher = _UnusedFetcher()
    crawler = WebCrawler(
        httpx_fetcher=httpx_fetcher,
        scrapling_fetcher=scrapling_fetcher,
        cleaner=_UnusedCleaner(),
        content_cache_repository=_CacheRepository(values),
        concurrency=1,
    )

    results = await crawler.crawl(
        seed_url,
        user_id=user_id,
        session_id="s1",
        max_pages=2,
        max_depth=1,
    )

    assert [result.source_url for result in results] == [seed_url, child_url]
    assert [result.markdown for result in results] == ["# Seed", "# Child"]
    assert httpx_fetcher.calls == 0
    assert scrapling_fetcher.calls == 0


def _cache_value(
        *,
        user_id: str,
        url: str,
        raw_html: str,
        markdown: str,
        title: str,
) -> WebContentCacheValue:
    return WebContentCacheValue(
        user_id=user_id,
        canonical_url=url,
        final_url=url,
        cache_mode=WebContentCacheMode.PUBLIC,
        status_code=200,
        content_type="text/html",
        raw_html=raw_html,
        markdown=markdown,
        expire_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        metadata={"title": title},
    )
