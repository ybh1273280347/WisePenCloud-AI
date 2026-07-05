from __future__ import annotations

import sys
import types
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

web_fetch_module = types.ModuleType("chat.application.tools.web_tools.web_fetch")
web_fetch_module.__path__ = [str(WEB_TOOLS_ROOT / "web_fetch")]
web_fetch_module.FetchCoordinator = object
sys.modules["chat.application.tools.web_tools.web_fetch"] = web_fetch_module

from chat.application.tools.web_tools.web_fetch.models import (  # noqa: E402
    WebFetchBatchResult,
    WebFetchResult,
)
from chat.application.tools.core import ToolExecutionError  # noqa: E402
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
        urls=["https://example.com/page"],
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


@pytest.mark.asyncio
async def test_web_fetch_rejects_unsafe_direct_url() -> None:
    tool = WebFetchTool(
        service=_FakeFetchService(),
        candidate_repository=_UnusedCandidateRepository(),
    )

    with pytest.raises(ToolExecutionError) as exc_info:
        await tool.execute(
            {"user_id": "u1", "session_id": "s1"},
            urls=["http://127.0.0.1/admin"],
        )

    assert exc_info.value.reason == "invalid_url"
