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

from chat.application.tools.core import ExactlyOneOfCheck, ToolInvocation
from chat.application.tools.session_tools.tool_content_read.models import (
    ToolContentReadResult,
)
from chat.application.tools.session_tools.tool_content_read_tool import ToolContentReadTool


class _FakeReadService:
    def __init__(self) -> None:
        self.called: str | None = None

    async def read_ranked_expand(self, **_: object) -> ToolContentReadResult:
        self.called = "ranked_expand"
        return ToolContentReadResult()

    async def read_regex_match(self, **_: object) -> ToolContentReadResult:
        self.called = "regex_match"
        return ToolContentReadResult()


@pytest.mark.asyncio
async def test_tool_content_read_query_pattern_one_of_preflight() -> None:
    tool = ToolContentReadTool(content_store=object())

    result = await ExactlyOneOfCheck().check(
        ToolInvocation(
            tool_call_id="call_1",
            tool_name="tool_content_read",
            tool_call_arguments={
                "content_ids": ["cnt_1"],
                "mode": "ranked_expand",
                "query": "what matters",
                "pattern": "what.*",
            },
        ),
        tool.definition.policy,
        tool.definition.llm_spec.parameters_schema,
        {"session_id": "s1"},
    )

    assert result.ok is False
    assert result.message == "Provide exactly one of query or pattern."


@pytest.mark.asyncio
async def test_tool_content_read_dispatches_ranked_expand() -> None:
    service = _FakeReadService()
    tool = ToolContentReadTool(content_store=object())
    tool._service = service

    await tool.execute(
        {"session_id": "s1"},
        content_ids=["cnt_1"],
        mode="ranked_expand",
        query="what matters",
    )

    assert service.called == "ranked_expand"


@pytest.mark.asyncio
async def test_tool_content_read_dispatches_regex_match() -> None:
    service = _FakeReadService()
    tool = ToolContentReadTool(content_store=object())
    tool._service = service

    await tool.execute(
        {"session_id": "s1"},
        content_ids=["cnt_1"],
        mode="regex_match",
        pattern="what.*",
    )

    assert service.called == "regex_match"
