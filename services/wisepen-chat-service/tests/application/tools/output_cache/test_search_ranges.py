import asyncio
import json

import pytest

from chat.application.tools.core import ToolExecutionError
from chat.application.tools.core.execution.executor import ToolExecutor
from chat.application.tools.core.output_cache.cache_store import StoredToolContent
from chat.application.tools.session_tools.tool_output import (
    read_by_range,
    search_by_regex,
)
from chat.application.tools.session_tools.tool_output.read_by_range import (
    _read_range,
)
from chat.application.tools.session_tools.tool_output.search_by_regex import (
    _search_by_regex,
)


def test_range_read_caps_large_requested_interval_and_returns_continuation_offsets():
    result = _read_range(
        "0123456789",
        start=1,
        end=100_000_000,
        char_budget=4,
    )

    assert result.text == "1234"
    assert result.start_offset == 1
    assert result.end_offset == 5


def test_regex_results_continue_from_the_last_match_without_rescanning_prefix():
    stored = StoredToolContent("c", "s", "x" + ("a" * 500 + "x") * 19)
    first = asyncio.run(
        _search_by_regex(stored=stored, pattern="x", start_offset=0)
    )
    second = asyncio.run(
        _search_by_regex(
            stored=stored,
            pattern="x",
            start_offset=first.next_offset,
        )
    )

    assert first.content_id == "c"
    assert first.next_offset == 4510
    assert first.has_more is True
    assert len(first.windows) == 10
    assert second.next_offset == len(stored.text)
    assert second.has_more is True
    assert len(second.windows) == 10


def test_regex_contexts_merge_only_when_expanded_ranges_intersect():
    overlapping = StoredToolContent("overlap", "s", "x" + "a" * 299 + "x")
    separated = StoredToolContent("gap", "s", "x" + "a" * 500 + "x")

    merged = asyncio.run(
        _search_by_regex(stored=overlapping, pattern="x", start_offset=0)
    )
    distinct = asyncio.run(
        _search_by_regex(stored=separated, pattern="x", start_offset=0)
    )

    assert len(merged.windows) == 1
    assert merged.windows[0].text.count("x") == 2
    assert merged.windows[0].matched_count == 2
    assert not hasattr(merged.windows[0], "highlights")
    assert len(distinct.windows) == 2
    assert [window.matched_count for window in distinct.windows] == [1, 1]

    serialized = json.loads(ToolExecutor._coerce_tool_output(merged).content)
    assert "highlights" not in serialized["windows"][0]
    assert serialized["windows"][0]["matched_count"] == 2
    assert serialized["content_id"] == "overlap"


def test_regex_context_prefers_chinese_sentence_boundary_and_falls_back_to_limit():
    sentence_text = "前文。" + "a" * 50 + "目标" + "b" * 60 + "后文。"
    sentence = StoredToolContent("sentence", "s", sentence_text)
    fallback_text = "a" * 500 + "目标" + "b" * 500
    fallback = StoredToolContent("fallback", "s", fallback_text)

    sentence_result = asyncio.run(
        _search_by_regex(stored=sentence, pattern="目标", start_offset=0)
    )
    fallback_result = asyncio.run(
        _search_by_regex(stored=fallback, pattern="目标", start_offset=0)
    )

    assert sentence_result.windows[0].start_offset == len("前文。")
    assert sentence_result.windows[0].text.startswith("a")
    assert sentence_result.windows[0].text.endswith("后文。")
    assert len(fallback_result.windows[0].text) <= 404


def test_regex_no_matches_returns_an_empty_result():
    result = asyncio.run(
        _search_by_regex(
            stored=StoredToolContent("c", "s", "nothing here"),
            pattern="missing",
            start_offset=0,
        )
    )

    assert result.has_more is False
    assert result.windows == []
    assert result.next_offset == len("nothing here")


def test_regex_stops_at_requested_match_count_and_passes_the_resume_position(monkeypatch):
    stored = StoredToolContent("c", "s", "x" * 50)
    compiled = search_by_regex.regex.compile("x")
    calls = []

    class Search:
        def finditer(self, text, *, pos, timeout):
            calls.append(pos)
            for index, matched in enumerate(compiled.finditer(text, pos=pos)):
                # 第十一个命中不得被消费，否则就没有在十个命中处停止。
                assert index < 10
                yield matched

    monkeypatch.setattr(search_by_regex.regex, "compile", lambda pattern: Search())
    first = asyncio.run(
        _search_by_regex(stored=stored, pattern="x", start_offset=0, max_matches=10)
    )
    second = asyncio.run(
        _search_by_regex(
            stored=stored,
            pattern="x",
            start_offset=first.next_offset,
            max_matches=10,
        )
    )
    assert calls == [0, 10]
    assert second.next_offset == 20
    assert second.has_more is True


def test_regex_allows_up_to_one_hundred_matches_and_rejects_larger_schema_values():
    stored = StoredToolContent("c", "s", "x" * 120)
    result = asyncio.run(
        _search_by_regex(stored=stored, pattern="x", start_offset=0, max_matches=100)
    )
    assert sum(window.matched_count for window in result.windows) == 100
    assert result.windows[0].matched_count == 100
    assert result.has_more is True
    schema = search_by_regex.SearchToolOutputRegexTool().definition.llm_spec.parameters_schema.raw
    assert schema["properties"]["max_matches"]["default"] == 10
    assert schema["properties"]["max_matches"]["maximum"] == 100


def test_regex_exactly_ten_matches_can_end_with_an_empty_followup():
    stored = StoredToolContent("c", "s", "x" * 10)
    first = asyncio.run(_search_by_regex(stored=stored, pattern="x", start_offset=0))
    final = asyncio.run(
        _search_by_regex(stored=stored, pattern="x", start_offset=first.next_offset)
    )
    assert first.has_more is True
    assert final.windows == []
    assert final.has_more is False
    assert final.next_offset == len(stored.text)


def test_regex_zero_width_matches_advance_past_end_of_source():
    stored = StoredToolContent("c", "s", "a" * 11)
    first = asyncio.run(_search_by_regex(stored=stored, pattern="(?=a)|$", start_offset=0))
    final = asyncio.run(
        _search_by_regex(stored=stored, pattern="(?=a)|$", start_offset=first.next_offset)
    )
    assert first.next_offset == 10
    assert first.has_more is True
    assert final.next_offset == len(stored.text) + 1
    assert final.has_more is False
    beyond = asyncio.run(
        _search_by_regex(stored=stored, pattern="(?=a)|$", start_offset=final.next_offset)
    )
    assert beyond.windows == []
    assert beyond.has_more is False


def test_regex_absolute_offset_preserves_lookbehind_and_anchor_semantics():
    stored = StoredToolContent("c", "s", "prefix target")
    result = asyncio.run(
        _search_by_regex(stored=stored, pattern="(?<=prefix )target", start_offset=7)
    )
    assert len(result.windows) == 1
    anchored = asyncio.run(
        _search_by_regex(stored=stored, pattern="^target", start_offset=7)
    )
    assert anchored.windows == []


@pytest.mark.asyncio
async def test_regex_tool_reads_one_session_content_and_reports_input_errors(monkeypatch):
    stored = StoredToolContent("c", "s", "x")

    async def get_content(*, content_id, session_id):
        assert session_id == "s"
        return stored if content_id == "c" else None

    monkeypatch.setattr(search_by_regex, "get_tool_content", get_content)
    tool = search_by_regex.SearchToolOutputRegexTool()
    result = await tool.execute(
        {"session_id": "s"},
        content_id="c",
        pattern="x",
        start_offset=0,
        max_matches=10,
    )
    assert result.content_id == "c"
    with pytest.raises(ToolExecutionError) as invalid:
        await tool.execute(
            {"session_id": "s"},
            content_id="c",
            pattern="[",
            start_offset=0,
            max_matches=10,
        )
    assert invalid.value.reason == "invalid_regex_pattern"
    with pytest.raises(ToolExecutionError) as missing:
        await tool.execute(
            {"session_id": "s"},
            content_id="missing",
            pattern="x",
            start_offset=0,
            max_matches=10,
        )
    assert missing.value.reason == "cached_tool_output_not_found"


@pytest.mark.asyncio
async def test_range_result_reports_continuation_for_the_requested_interval(monkeypatch):
    stored = StoredToolContent("c", "s", "0123456789")

    async def get_content(*, content_id, session_id):
        return stored

    monkeypatch.setattr(read_by_range, "get_tool_content", get_content)
    monkeypatch.setattr(read_by_range.settings, "TOOL_CONTENT_READ_WINDOW_CHAR_BUDGET", 4)
    tool = read_by_range.ReadToolOutputRangeTool()
    first = await tool.execute({"session_id": "s"}, content_id="c", start=1, end=7)
    final = await tool.execute(
        {"session_id": "s"}, content_id="c", start=first.next_offset, end=7
    )
    assert first.window.text == "1234"
    assert first.next_offset == 5
    assert first.has_more is True
    assert final.window.text == "56"
    assert final.next_offset == 7
    assert final.has_more is False
