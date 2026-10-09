import asyncio

from chat.application.tools.core.output_cache.cache_store import StoredToolContent
from chat.application.tools.session_tools.cached_tool_output_tools.read_by_range import (
    _read_range,
)
from chat.application.tools.session_tools.cached_tool_output_tools.search_by_regex import (
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
    assert result.truncated is True


def test_regex_results_are_paginated_in_input_order_at_fifteen_matches():
    stored = StoredToolContent("c", "s", "x " * 20)
    first = asyncio.run(
        _search_by_regex(stored_items=[stored], pattern="x", offset=0)
    )
    second = asyncio.run(
        _search_by_regex(stored_items=[stored], pattern="x", offset=1)
    )

    assert first.matched_count == 15
    assert first.has_more is True
    assert second.matched_count == 5
    assert second.has_more is False


def test_regex_contexts_merge_only_when_expanded_ranges_intersect():
    overlapping = StoredToolContent("overlap", "s", "x" + "a" * 299 + "x")
    separated = StoredToolContent("gap", "s", "x" + "a" * 500 + "x")

    merged = asyncio.run(
        _search_by_regex(stored_items=[overlapping], pattern="x", offset=0)
    )
    distinct = asyncio.run(
        _search_by_regex(stored_items=[separated], pattern="x", offset=0)
    )

    assert len(merged.windows) == 1
    assert len(merged.windows[0].highlights) == 2
    assert len(distinct.windows) == 2


def test_regex_context_prefers_chinese_sentence_boundary_and_falls_back_to_limit():
    sentence_text = "前文。" + "a" * 50 + "目标" + "b" * 60 + "后文。"
    sentence = StoredToolContent("sentence", "s", sentence_text)
    fallback_text = "a" * 500 + "目标" + "b" * 500
    fallback = StoredToolContent("fallback", "s", fallback_text)

    sentence_result = asyncio.run(
        _search_by_regex(stored_items=[sentence], pattern="目标", offset=0)
    )
    fallback_result = asyncio.run(
        _search_by_regex(stored_items=[fallback], pattern="目标", offset=0)
    )

    assert sentence_result.windows[0].start_offset == len("前文。")
    assert sentence_result.windows[0].text.startswith("a")
    assert sentence_result.windows[0].text.endswith("后文。")
    assert len(fallback_result.windows[0].text) <= 404


def test_regex_no_matches_returns_an_empty_page():
    result = asyncio.run(
        _search_by_regex(
            stored_items=[StoredToolContent("c", "s", "nothing here")],
            pattern="missing",
            offset=0,
        )
    )

    assert result.matched_count == 0
    assert result.has_more is False
    assert result.windows == []
