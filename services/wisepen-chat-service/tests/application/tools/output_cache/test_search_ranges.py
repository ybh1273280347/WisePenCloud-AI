import re

from chat.application.tools.core.output_cache.cache_store import StoredToolContent
from chat.application.tools.session_tools.cached_tool_output_tools.search_by_regex import (
    _build_regex_windows,
)
from chat.application.tools.session_tools.cached_tool_output_tools.search_by_relevance import (
    _format_range,
    _window_from_span,
)
from chat.application.tools.session_tools.cached_tool_output_tools.window import (
    CachedToolOutputWindowBuilder,
)
from common.utils.markdown import SourceSpan


def test_regex_offsets_round_trip_to_range():
    stored = StoredToolContent("c", "s", "前文🙂。这里有 target。后文。")
    matches = [
        (stored, match.start(), match.end())
        for match in re.finditer("target", stored.text)
    ]
    windows = _build_regex_windows(matched_ranges=matches)
    window = windows[0].window
    reread = CachedToolOutputWindowBuilder(char_budget=100).build_range_window(
        stored,
        start=window.start_offset,
        end=window.end_offset,
    )
    assert reread.text == window.text
    highlight = windows[0].highlights[0]
    assert window.text[highlight.start_offset : highlight.end_offset] == "target"


def test_relevance_range_remains_a_character_interval():
    stored = StoredToolContent("c", "s", "🙂0123456789")
    span = SourceSpan(2, 7)
    window = _window_from_span(
        stored=stored, span=span, scope=SourceSpan(0, len(stored.text))
    )
    start, end = map(int, _format_range(span).split(" - "))
    reread = CachedToolOutputWindowBuilder(char_budget=100).build_range_window(
        stored,
        start=start,
        end=end,
    )
    assert reread.text == window.text == "12345"
