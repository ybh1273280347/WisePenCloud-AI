from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

common_module = types.ModuleType("common")
logger_module = types.ModuleType("common.logger")
logger_module.warn = lambda *args, **kwargs: None
logger_module.info = lambda *args, **kwargs: None
logger_module.error = lambda *args, **kwargs: None
common_module.logger = logger_module
sys.modules.setdefault("common", common_module)
sys.modules["common.logger"] = logger_module

from chat.application.tools.web_tools.web_fetch.models import (  # noqa: E402
    WebFetchBatchResult,
    WebFetchResult,
)
from chat.application.tools.web_tools.web_fetch_tool import WebFetchTool  # noqa: E402


class _FakeFetchService:
    async def fetch_many(self, *_: object, **__: object) -> WebFetchBatchResult:
        return WebFetchBatchResult(
            items=(
                WebFetchResult(
                    source_url="https://example.test/page",
                    final_url="https://cdn.example.test/page",
                    status_code=200,
                    content_type="text/html",
                    title="Example Page",
                    markdown="# Example Page",
                ),
                WebFetchResult(
                    source_url="https://example.test/file.pdf",
                    final_url="https://cdn.example.test/file.pdf",
                    status_code=200,
                    content_type="application/pdf",
                    title=None,
                    markdown=None,
                    file_ref="tfile_abc",
                    file_label="pdf",
                ),
            ),
        )


class _UnusedCandidateRepository:
    pass


@pytest.mark.asyncio
async def test_web_fetch_visible_result_hides_internal_fetch_metadata() -> None:
    tool = WebFetchTool(
        service=_FakeFetchService(),
        candidate_repository=_UnusedCandidateRepository(),
    )

    result = await tool.execute(
        {"user_id": "u1", "session_id": "s1"},
        urls=["https://example.test/page"],
    )

    assert result.visible_result["items"] == (
        {
            "source_url": "https://example.test/page",
            "title": "Example Page",
        },
        {
            "source_url": "https://example.test/file.pdf",
            "file_ref": "tfile_abc",
            "file_label": "pdf",
        },
    )
    assert "warnings" not in result.visible_result
    for item in result.visible_result["items"]:
        assert "final_url" not in item
        assert "status_code" not in item
        assert "content_type" not in item
        assert "source_scope" not in item
    assert result.cacheable_texts == ("# Example Page",)
