from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from chat.application.tools.common.web_content_cache import (
    HtmlCacheWrite,
    NonHtmlCacheStubWrite,
    WebContentCacheMode,
    WebContentCacheService,
    WebContentCacheValue,
)


class FakeWebContentCacheRepository:
    def __init__(self) -> None:
        self.values: dict[tuple[WebContentCacheMode, str], WebContentCacheValue] = {}

    async def get_value(
            self,
            *,
            user_id: str,
            url: str,
            cache_mode: WebContentCacheMode | str,
    ) -> WebContentCacheValue | None:
        return self.values.get((WebContentCacheMode(cache_mode), url.strip()))

    async def set_value(self, value: WebContentCacheValue) -> None:
        self.values[(value.cache_mode, value.canonical_url.strip())] = value

    async def delete_value(
            self,
            *,
            user_id: str,
            url: str,
            cache_mode: WebContentCacheMode | str,
    ) -> None:
        self.values.pop((WebContentCacheMode(cache_mode), url.strip()), None)


@pytest.mark.asyncio
async def test_html_markdown_cache_roundtrip_keeps_raw_html() -> None:
    repository = FakeWebContentCacheRepository()
    service = WebContentCacheService(repository=repository)

    written = await service.write_html_markdown(
        HtmlCacheWrite(
            url="https://example.com/page",
            user_id="user-1",
            source_scope="web_public",
            status_code=200,
            content_type="text/html",
            raw_html="<html><body>Hello</body></html>",
            markdown="# Hello",
            title="Hello",
            headers={"cache-control": "max-age=60"},
            fetcher="httpx",
            cleaner="trafilatura",
            producer="web_fetch",
        )
    )

    cached = await service.read_markdown_page(url="https://example.com/page", user_id="user-1")

    assert written is True
    assert cached is not None
    assert cached.markdown == "# Hello"
    assert cached.raw_html == "<html><body>Hello</body></html>"
    assert cached.title == "Hello"
    assert cached.cache_mode == WebContentCacheMode.PUBLIC


@pytest.mark.asyncio
async def test_non_html_stub_can_be_filled_by_source_metadata() -> None:
    repository = FakeWebContentCacheRepository()
    service = WebContentCacheService(repository=repository)

    await service.write_non_html_stub(
        NonHtmlCacheStubWrite(
            user_id="user-1",
            source_scope="web_public",
            source_url="https://example.com/report.pdf",
            status_code=200,
            content_type="application/pdf",
            headers={"cache-control": "max-age=60"},
            fetcher="httpx",
            file_label="pdf",
        )
    )
    metadata = {
        "source_kind": "web_fetch",
        "source_scope": "web_public",
        "source_url": "https://example.com/report.pdf",
    }

    written = await service.write_markdown_from_metadata(
        user_id="user-1",
        metadata=metadata,
        content_type="application/pdf",
        markdown="# Parsed PDF",
        parser="document_parse",
        parser_version="document_parse:v1",
    )
    cached = await service.read_markdown_by_metadata(
        user_id="user-1",
        metadata=metadata,
        parser_version="document_parse:v1",
    )

    assert written is True
    assert cached is not None
    assert cached.markdown == "# Parsed PDF"
    assert cached.content_type == "application/pdf"


@pytest.mark.asyncio
async def test_expired_value_is_not_returned() -> None:
    repository = FakeWebContentCacheRepository()
    service = WebContentCacheService(repository=repository)
    await repository.set_value(
        WebContentCacheValue(
            user_id="user-1",
            canonical_url="https://example.com/old",
            cache_mode=WebContentCacheMode.PUBLIC,
            status_code=200,
            content_type="text/html",
            markdown="# Old",
            expire_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
    )

    cached = await service.read_markdown_page(url="https://example.com/old", user_id="user-1")

    assert cached is None
