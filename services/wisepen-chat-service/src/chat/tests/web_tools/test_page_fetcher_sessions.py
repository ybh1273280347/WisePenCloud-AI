from __future__ import annotations

from types import SimpleNamespace

import pytest

from chat.application.tools.web_tools.fetch_services.fetchers.static_page_fetcher import StaticPageFetcher
from chat.application.tools.web_tools.fetch_services.fetchers.stealthy_page_fetcher import StealthyPageFetcher


@pytest.mark.asyncio
async def test_static_page_fetcher_uses_injected_session() -> None:
    session = _FakeStaticSession()
    fetcher = StaticPageFetcher(session=session)

    first = await fetcher.fetch("https://example.com/one")
    second = await fetcher.fetch("https://example.com/two")

    assert first.fetcher == "static_page"
    assert second.fetcher == "static_page"
    assert session.calls == [
        "https://example.com/one",
        "https://example.com/two",
    ]


@pytest.mark.asyncio
async def test_stealthy_page_fetcher_uses_injected_session() -> None:
    session = _FakeStealthySession()
    fetcher = StealthyPageFetcher(session=session)

    first = await fetcher.fetch("https://example.com/one")
    second = await fetcher.fetch("https://example.com/two")

    assert first.fetcher == "stealthy_page"
    assert second.fetcher == "stealthy_page"
    assert session.calls == [
        "https://example.com/one",
        "https://example.com/two",
    ]


class _FakeStaticSession:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def get(self, url: str, **_: object) -> SimpleNamespace:
        self.calls.append(url)
        return _response(url)


class _FakeStealthySession:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def fetch(self, url: str, **_: object) -> SimpleNamespace:
        self.calls.append(url)
        return _response(url)


def _response(url: str) -> SimpleNamespace:
    return SimpleNamespace(
        status=200,
        body=b"<html><body>content</body></html>",
        headers={"content-type": "text/html"},
        history=(),
        url=url,
        encoding="utf-8",
    )
