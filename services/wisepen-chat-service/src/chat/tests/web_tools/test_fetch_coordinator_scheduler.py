from __future__ import annotations

import asyncio

import pytest

from chat.application.tools.web_tools.fetch_services.cleaners.base import CleanedOutput
from chat.application.tools.web_tools.fetch_services.core.errors import (  # noqa: E402
    UrlFetchNetworkError,
)
from chat.application.tools.web_tools.fetch_services.core.models import RawFetchOutput
from chat.application.tools.web_tools.fetch_services.web_fetch import FetchCoordinator


@pytest.mark.asyncio
async def test_fetch_many_releases_file_sniff_worker_when_scrapling_page_fetch_is_pending() -> None:
    scrapling_started = asyncio.Event()
    release_scrapling = asyncio.Event()
    fast_sniff_seen = asyncio.Event()
    static_fetcher = _SchedulerStaticFetcher(fast_fetch_seen=fast_sniff_seen)
    stealthy_fetcher = _BlockingScraplingFetcher(
        started=scrapling_started,
        release=release_scrapling,
    )
    coordinator = FetchCoordinator(
        static_fetcher=static_fetcher,
        stealthy_fetcher=stealthy_fetcher,
        temp_file_downloader=object(),
        cleaner=_EchoCleaner(),
        file_store=_UnusedFileStore(),
        batch_concurrency=1,
        stealthy_concurrency=1,
        max_stealthy_fallbacks=1,
        min_text_length=40,
    )

    fetch_task = asyncio.create_task(
        coordinator.fetch_many(
            [
                "https://example.test/slow",
                "https://example.test/fast",
            ],
            user_id="u1",
            session_id="s1",
        )
    )

    await asyncio.wait_for(scrapling_started.wait(), timeout=1)
    await asyncio.wait_for(fast_sniff_seen.wait(), timeout=1)
    assert not fetch_task.done()

    release_scrapling.set()
    result = await asyncio.wait_for(fetch_task, timeout=1)

    assert [item.source_url for item in result.items] == [
        "https://example.test/slow",
        "https://example.test/fast",
    ]
    assert result.failed == ()
    assert static_fetcher.calls == [
        "https://example.test/slow",
        "https://example.test/fast",
    ]


@pytest.mark.asyncio
async def test_fetch_many_does_not_enqueue_fallback_after_scrapling_cap() -> None:
    stealthy_fetcher = _CountingScraplingFetcher()
    coordinator = FetchCoordinator(
        static_fetcher=_AlwaysFailingStaticFetcher(),
        stealthy_fetcher=stealthy_fetcher,
        temp_file_downloader=object(),
        cleaner=_EchoCleaner(),
        file_store=_UnusedFileStore(),
        batch_concurrency=2,
        stealthy_concurrency=1,
        max_stealthy_fallbacks=1,
        min_text_length=40,
    )

    result = await coordinator.fetch_many(
        [
            "https://example.test/one",
            "https://example.test/two",
        ],
        user_id="u1",
        session_id="s1",
    )

    assert len(result.items) == 1
    assert len(result.failed) == 1
    assert result.failed[0].reason == "fallback_not_admitted: max_stealthy_fallbacks_reached"
    assert stealthy_fetcher.calls == ["https://example.test/one"]


@pytest.mark.asyncio
async def test_fetch_many_returns_completed_results_when_tool_timeout_cancels_batch() -> None:
    release_slow = asyncio.Event()
    coordinator = FetchCoordinator(
        static_fetcher=_OneFastOneBlockingStaticFetcher(release_slow=release_slow),
        stealthy_fetcher=_CountingScraplingFetcher(),
        temp_file_downloader=object(),
        cleaner=_EchoCleaner(),
        file_store=_UnusedFileStore(),
        batch_concurrency=2,
        stealthy_concurrency=1,
        max_stealthy_fallbacks=0,
        min_text_length=1,
    )

    result = await asyncio.wait_for(
        coordinator.fetch_many(
            [
                "https://example.test/fast",
                "https://example.test/slow",
            ],
            user_id="u1",
            session_id="s1",
        ),
        timeout=0.05,
    )

    assert [item.source_url for item in result.items] == ["https://example.test/fast"]
    assert [(item.url, item.reason) for item in result.failed] == [
        ("https://example.test/slow", "fetch_timed_out"),
    ]
    assert "tool timed out; returning completed results" in result.warnings

    release_slow.set()


class _EchoCleaner:
    @property
    def name(self) -> str:
        return "echo"

    def clean(self, raw_html: str, *, url: str | None = None) -> CleanedOutput:
        return CleanedOutput(
            markdown=raw_html,
            title=url,
            cleaner=self.name,
        )


class _SchedulerStaticFetcher:
    def __init__(self, *, fast_fetch_seen: asyncio.Event) -> None:
        self._fast_fetch_seen = fast_fetch_seen
        self.calls: list[str] = []

    @property
    def name(self) -> str:
        return "static"

    async def fetch(self, url: str) -> RawFetchOutput:
        self.calls.append(url)
        if url.endswith("/fast"):
            self._fast_fetch_seen.set()
            return _raw(url, raw_html="static content " * 10, fetcher=self.name)
        raise UrlFetchNetworkError(url=url, reason="network")


class _AlwaysFailingStaticFetcher:
    @property
    def name(self) -> str:
        return "static"

    async def fetch(self, url: str) -> RawFetchOutput:
        raise UrlFetchNetworkError(url=url, reason="network")


class _BlockingScraplingFetcher:
    def __init__(self, *, started: asyncio.Event, release: asyncio.Event) -> None:
        self._started = started
        self._release = release

    @property
    def name(self) -> str:
        return "scrapling"

    async def fetch(self, url: str) -> RawFetchOutput:
        self._started.set()
        await self._release.wait()
        return _raw(url, raw_html="fallback content " * 10, fetcher=self.name)


class _OneFastOneBlockingStaticFetcher:
    def __init__(self, *, release_slow: asyncio.Event) -> None:
        self._release_slow = release_slow

    @property
    def name(self) -> str:
        return "static"

    async def fetch(self, url: str) -> RawFetchOutput:
        if url.endswith("/slow"):
            await self._release_slow.wait()
        return _raw(url, raw_html="static content " * 10, fetcher=self.name)


class _CountingScraplingFetcher:
    def __init__(self) -> None:
        self.calls: list[str] = []

    @property
    def name(self) -> str:
        return "scrapling"

    async def fetch(self, url: str) -> RawFetchOutput:
        self.calls.append(url)
        return _raw(url, raw_html="fallback content " * 10, fetcher=self.name)


class _UnusedFileStore:
    pass


def _raw(url: str, *, raw_html: str, fetcher: str = "httpx") -> RawFetchOutput:
    return RawFetchOutput(
        source_url=url,
        fetcher=fetcher,
        status_code=200,
        content_type="text/html",
        raw_html=raw_html,
    )
