from __future__ import annotations

import pytest

from chat.application.tools.web_tools.fetch_services.core.models import (
    WebFetchBatchResult,
    WebFetchFailure,
    WebFetchResult,
)
from chat.application.tools.web_tools.web_fetch_tool import WebFetchTool


class _FakeFetchService:
    def __init__(self, result: WebFetchBatchResult | None = None) -> None:
        self.result = result or WebFetchBatchResult()
        self.calls: list[list[str]] = []

    async def fetch_many(self, urls: list[str], **__: object) -> WebFetchBatchResult:
        self.calls.append(urls)
        return self.result


def _batch_result() -> WebFetchBatchResult:
    return WebFetchBatchResult(
        items=(
            WebFetchResult(
                source_url="https://example.test/page",
                status_code=200,
                content_type="text/html",
                title="Example Page",
                markdown="# Example Page",
                warnings=("httpx_fallback: http 403",),
            ),
            WebFetchResult(
                source_url="https://example.test/file.pdf",
                status_code=200,
                content_type="application/pdf",
                title=None,
                markdown=None,
                file_ref="file_abc",
                file_label="pdf",
                warnings=("file handoff",),
            ),
        ),
        failed=(
            WebFetchFailure(
                url="https://example.test/missing",
                reason="http 404",
            ),
        ),
        warnings=("1/2 urls used fallback",),
    )


@pytest.mark.asyncio
async def test_web_fetch_visible_result_hides_internal_fetch_metadata() -> None:
    tool = WebFetchTool(service=_FakeFetchService(_batch_result()))

    result = await tool.execute(
        {"user_id": "u1", "session_id": "s1"},
        urls=["https://example.com/page"],
    )

    assert result.visible_result["items"] == (
        {
            "source_url": "https://example.test/page",
            "title": "Example Page",
        },
        {
            "source_url": "https://example.test/file.pdf",
            "file_ref": "file_abc",
            "file_label": "pdf",
        },
    )
    assert "warnings" not in result.visible_result
    assert "failed" not in result.visible_result
    for item in result.visible_result["items"]:
        assert "final_url" not in item
        assert "status_code" not in item
        assert "content_type" not in item
        assert "source_scope" not in item
        assert "warnings" not in item
    assert result.cacheable_texts == ("# Example Page",)


@pytest.mark.asyncio
async def test_web_fetch_skips_unsafe_url_without_interrupting_batch() -> None:
    service = _FakeFetchService(_batch_result())
    tool = WebFetchTool(service=service)

    result = await tool.execute(
        {"user_id": "u1", "session_id": "s1"},
        urls=["http://127.0.0.1/admin", "https://example.com/page"],
    )

    assert service.calls == [["https://example.com/page"]]
    assert result.visible_result["items"]
    assert "failed" not in result.visible_result


@pytest.mark.asyncio
async def test_web_fetch_distinguishes_all_invalid_urls() -> None:
    service = _FakeFetchService()
    tool = WebFetchTool(service=service)

    result = await tool.execute(
        {"user_id": "u1", "session_id": "s1"},
        urls=["http://127.0.0.1/admin"],
    )

    assert service.calls == []
    assert result.visible_result == {
        "items": (),
        "warning": "all_urls_invalid",
    }


@pytest.mark.asyncio
async def test_web_fetch_distinguishes_empty_fetch_result() -> None:
    service = _FakeFetchService()
    tool = WebFetchTool(service=service)

    result = await tool.execute(
        {"user_id": "u1", "session_id": "s1"},
        urls=["https://example.com/page"],
    )

    assert service.calls == [["https://example.com/page"]]
    assert result.visible_result == {
        "items": (),
        "warning": "no_results",
    }
