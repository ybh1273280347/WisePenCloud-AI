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
    ToolContentRegexReadRequest,
    ToolContentReadMatch,
    ToolContentReadResult,
    ToolContentRerankReadRequest,
    ToolContentSequentialReadResult,
    ToolContentSelector,
    ToolContentWindow,
)
from chat.application.tools.session_tools.tool_content_sequential_read_tool import (
    ToolContentSequentialReadTool,
)
from chat.application.tools.common.tool_content_store.core.models import (
    StoredToolContent,
    ToolContentChunk,
    ToolContentIndex,
    ToolContentIndexEntry,
)
from chat.application.tools.core import ToolExecutionError
from chat.application.tools.session_tools._tool_content_read_common import read_content_id_batches
from chat.application.tools.session_tools._tool_content_read_common import selector_from_payload
from chat.application.tools.session_tools.tool_content_regex_read_tool import ToolContentRegexReadTool
from chat.application.tools.session_tools.tool_content_rerank_read_tool import ToolContentRerankReadTool
from chat.application.tools.session_tools.tool_content_read.service import ToolContentReadService


class _FakeReadService:
    def __init__(self) -> None:
        self.called: str | None = None

    async def read_ranked_expand(self, **_: object) -> ToolContentReadResult:
        self.called = "ranked_expand"
        return ToolContentReadResult()

    async def read_regex_match(self, **_: object) -> ToolContentReadResult:
        self.called = "regex_match"
        return ToolContentReadResult()


class _FakeSequentialReadService:
    async def load_stored_content(self, **_: object) -> tuple[str, object]:
        return "cnt_1", object()

    def build_continuous_window(self, **_: object) -> ToolContentWindow:
        return ToolContentWindow(text="hello", start_offset=0, end_offset=5)


class _StoredContentStore:
    def __init__(self, stored: StoredToolContent) -> None:
        self._stored = stored

    async def canonicalize_content_id(self, *, content_id: str, session_id: str) -> tuple[str, str | None]:
        return content_id, None

    async def get(self, *, content_id: str, session_id: str) -> StoredToolContent | None:
        if content_id != self._stored.content_id or session_id != self._stored.session_id:
            return None
        return self._stored


def test_tool_content_rerank_read_schema_has_no_mode() -> None:
    tool = ToolContentRerankReadTool(content_store=object())
    schema = tool.definition.llm_spec.parameters_schema

    assert tool.definition.llm_spec.name == "tool_content_rerank_read"
    assert schema.required == ("content_ids", "query")
    assert "mode" not in schema.properties
    assert "pattern" not in schema.properties


def test_tool_content_rerank_read_schema_uses_default_top_k() -> None:
    tool = ToolContentRerankReadTool(content_store=object())
    schema = tool.definition.llm_spec.parameters_schema

    assert schema.properties["top_k"]["default"] == 10


def test_tool_content_regex_read_schema_has_no_mode() -> None:
    tool = ToolContentRegexReadTool(content_store=object())
    schema = tool.definition.llm_spec.parameters_schema

    assert tool.definition.llm_spec.name == "tool_content_regex_read"
    assert schema.required == ("content_ids", "pattern")
    assert "mode" not in schema.properties
    assert "query" not in schema.properties


def test_tool_content_regex_read_schema_uses_default_max_matches() -> None:
    tool = ToolContentRegexReadTool(content_store=object())
    schema = tool.definition.llm_spec.parameters_schema

    assert schema.properties["max_matches"]["default"] == 10


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
async def test_tool_content_sequential_read_returns_dataclass_result() -> None:
    tool = ToolContentSequentialReadTool(content_store=object())
    tool._service = _FakeSequentialReadService()

    result = await tool.execute(
        {"session_id": "s1"},
        content_id="cnt_1",
        offset=0,
        limit=5,
    )

    assert result == ToolContentSequentialReadResult(
        content_id="cnt_1",
        status="success",
        window=ToolContentWindow(text="hello", start_offset=0, end_offset=5),
    )


@pytest.mark.asyncio
async def test_tool_content_regex_read_reports_invalid_regex_pattern() -> None:
    tool = ToolContentRegexReadTool(content_store=object())

    with pytest.raises(ToolExecutionError) as exc_info:
        await tool.execute(
            {"session_id": "s1"},
            content_ids=["cnt_1"],
            pattern="[",
        )

    assert exc_info.value.reason == "invalid_regex_pattern"


@pytest.mark.asyncio
async def test_tool_content_regex_read_deduplicates_matches_by_chunk() -> None:
    service = ToolContentReadService(
        store=_StoredContentStore(_stored_content()),
        ranking_engine=object(),
    )

    result = await service.read_regex_match(
        request=ToolContentRegexReadRequest(
            content_ids=("cnt_1",),
            pattern="alpha",
            selector=ToolContentSelector(chunk_indices=(0,)),
            max_matches=10,
        ),
        session_id="s1",
    )

    assert [match.window.center_chunk for match in result.matches if match.window] == [0]


def test_tool_content_selector_intersects_chunk_indices_and_block_kinds() -> None:
    service = ToolContentReadService(
        store=_StoredContentStore(_stored_content()),
        ranking_engine=object(),
    )
    selected = service._select_chunks(
        _stored_content(),
        ToolContentSelector(
            chunk_indices=(0, 1),
            block_kinds=("table",),
        ),
    )

    assert [chunk.chunk_index for chunk in selected] == [1]


def test_tool_content_selector_matches_parent_heading_in_nested_section_path() -> None:
    stored = StoredToolContent(
        content_id="cnt_1",
        session_id="s1",
        content_type="text/markdown",
        text="# 一级\n\n## 二级\n\n正文。",
        chunks=(
            ToolContentChunk(
                chunk_index=0,
                start_offset=0,
                end_offset=16,
                section_path=("一级", "二级"),
            ),
        ),
        index=ToolContentIndex(
            entries=(
                ToolContentIndexEntry(
                    locator_name="section:一级 > 二级",
                    locator_kind="section",
                    chunk_indices=(0,),
                    section_path=("一级", "二级"),
                ),
            ),
        ),
    )
    service = ToolContentReadService(
        store=_StoredContentStore(stored),
        ranking_engine=object(),
    )

    selected = service._select_chunks(
        stored,
        ToolContentSelector(sections=("一级",)),
    )

    assert [chunk.chunk_index for chunk in selected] == [0]


def test_tool_content_selector_payload_ignores_invalid_coercions() -> None:
    selector = selector_from_payload(
        {
            "block_kinds": "code",
            "sections": [" Intro ", "", 123, True],
            "chunk_indices": [0, "1", True, 2],
            "include_unknown": "true",
        }
    )

    assert selector.block_kinds == ()
    assert selector.sections == ("Intro",)
    assert selector.chunk_indices == (0, 2)
    assert selector.include_unknown is False


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


@pytest.mark.asyncio
async def test_tool_content_read_batches_keeps_partial_results_after_batch_error() -> None:
    async def read_batch(request: ToolContentRerankReadRequest) -> ToolContentReadResult:
        content_id = request.content_ids[0]
        if content_id == "cnt_2":
            raise RuntimeError("temporary failure")
        return ToolContentReadResult(
            matches=(ToolContentReadMatch(content_id=content_id),)
        )

    result = await read_content_id_batches(
        request=ToolContentRerankReadRequest(
            content_ids=("cnt_1", "cnt_2", "cnt_3"),
            query="what matters",
        ),
        batch_size=1,
        read_batch=read_batch,
    )

    assert tuple(match.content_id for match in result.matches) == ("cnt_1", "cnt_3")
    assert tuple(match.content_id for match in result.failed) == ("cnt_2",)
    assert result.failed[0].reason == "RuntimeError"


def _stored_content() -> StoredToolContent:
    text = "alpha alpha\n\ntable alpha\n\nplain beta"
    return StoredToolContent(
        content_id="cnt_1",
        session_id="s1",
        content_type="text/markdown",
        text=text,
        chunks=(
            ToolContentChunk(
                chunk_index=0,
                start_offset=0,
                end_offset=11,
                block_kinds=("paragraph",),
            ),
            ToolContentChunk(
                chunk_index=1,
                start_offset=13,
                end_offset=24,
                block_kinds=("table",),
            ),
            ToolContentChunk(
                chunk_index=2,
                start_offset=26,
                end_offset=len(text),
                block_kinds=("paragraph",),
            ),
        ),
    )
