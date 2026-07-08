from __future__ import annotations

import os
import sys
import types
from pathlib import Path

import pytest

os.environ.setdefault("NACOS_SERVER_ADDR", "127.0.0.1:8848")

ranking_engine_stub = types.ModuleType("chat.application.utils.ranking_engine")
ranking_engine_stub.__path__ = [
    str(
        Path(__file__).resolve().parents[2]
        / "src"
        / "chat"
        / "application"
        / "utils"
        / "ranking_engine"
    )
]
sys.modules.setdefault("chat.application.utils.ranking_engine", ranking_engine_stub)

ranking_engine_registry_stub = types.ModuleType("chat.application.utils.ranking_engine.registry")
ranking_engine_registry_stub.get_ranking_engine = lambda _: object()
sys.modules.setdefault("chat.application.utils.ranking_engine.registry", ranking_engine_registry_stub)

from chat.application.tools.session_tools.tool_content_read.models import (
    ToolContentReadResult,
)
from chat.application.tools.session_tools.tool_content_regex_read_tool import ToolContentRegexReadTool
from chat.application.tools.session_tools.tool_content_rerank_read_tool import ToolContentRerankReadTool


class _FakeReadService:
    def __init__(self) -> None:
        self.called: str | None = None

    async def read_ranked_expand(self, **_: object) -> ToolContentReadResult:
        self.called = "ranked_expand"
        return ToolContentReadResult()

    async def read_regex_match(self, **_: object) -> ToolContentReadResult:
        self.called = "regex_match"
        return ToolContentReadResult()


def test_tool_content_rerank_read_schema_has_no_mode() -> None:
    tool = ToolContentRerankReadTool(content_store=object())
    schema = tool.definition.llm_spec.parameters_schema

    assert tool.definition.llm_spec.name == "tool_content_rerank_read"
    assert schema.required == ("content_ids", "query")
    assert "mode" not in schema.properties
    assert "pattern" not in schema.properties


def test_tool_content_regex_read_schema_has_no_mode() -> None:
    tool = ToolContentRegexReadTool(content_store=object())
    schema = tool.definition.llm_spec.parameters_schema

    assert tool.definition.llm_spec.name == "tool_content_regex_read"
    assert schema.required == ("content_ids", "pattern")
    assert "mode" not in schema.properties
    assert "query" not in schema.properties


@pytest.mark.asyncio
async def test_tool_content_rerank_read_dispatches_ranked_expand() -> None:
    service = _FakeReadService()
    tool = ToolContentRerankReadTool(content_store=object())
    tool._service = service

    await tool.execute(
        {"session_id": "s1"},
        content_ids=["cnt_1"],
        query="what matters",
    )

    assert service.called == "ranked_expand"


@pytest.mark.asyncio
async def test_tool_content_regex_read_dispatches_regex_match() -> None:
    service = _FakeReadService()
    tool = ToolContentRegexReadTool(content_store=object())
    tool._service = service

    await tool.execute(
        {"session_id": "s1"},
        content_ids=["cnt_1"],
        pattern="what.*",
    )

    assert service.called == "regex_match"
