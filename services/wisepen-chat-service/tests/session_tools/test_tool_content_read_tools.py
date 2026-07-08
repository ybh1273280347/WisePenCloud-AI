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
    ToolContentReadMatch,
    ToolContentReadResult,
    ToolContentRerankReadRequest,
)
from chat.application.tools.session_tools._tool_content_read_common import read_content_id_batches
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


@pytest.mark.asyncio
async def test_tool_content_read_batches_multiple_content_ids() -> None:
    seen_batches: list[tuple[str, ...]] = []

    async def read_batch(request: ToolContentRerankReadRequest) -> ToolContentReadResult:
        seen_batches.append(request.content_ids)
        return ToolContentReadResult(
            matches=tuple(
                ToolContentReadMatch(content_id=content_id)
                for content_id in request.content_ids
            )
        )

    result = await read_content_id_batches(
        request=ToolContentRerankReadRequest(
            content_ids=("cnt_1", "cnt_2", "cnt_3"),
            query="what matters",
        ),
        batch_size=2,
        read_batch=read_batch,
    )

    assert seen_batches == [("cnt_1", "cnt_2"), ("cnt_3",)]
    assert tuple(match.content_id for match in result.matches) == (
        "cnt_1",
        "cnt_2",
        "cnt_3",
    )
