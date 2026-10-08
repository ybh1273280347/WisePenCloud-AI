from chat.application.tools.core.output_cache.cache_store import (
    StoredToolContent,
    _build_cache_chunks,
)
from chat.application.tools.session_tools.cached_tool_output_tools.window import (
    CachedToolOutputWindowBuilder,
)
from common.utils.markdown import DocumentChunker, TiktokenTokenCounter


def test_chat_chunks_are_exact_nonoverlapping_source_windows():
    text = "# 标题\r\n\r\n" + "中文🙂 abc \u2028" * 1800 + "\r\n\r\n# End\nlast\n"
    result = DocumentChunker().chunk(text)
    counter = TiktokenTokenCounter()
    chunks = _build_cache_chunks(text, result.sections, result.anchors, counter)
    assert "".join(chunk.text for chunk in chunks) == text
    assert len(chunks) > 2
    for index, chunk in enumerate(chunks):
        assert chunk.text == text[chunk.start_offset : chunk.end_offset]
        assert chunk.chunk_index == index
        assert counter.count(chunk.text) <= 1600
        if index:
            assert chunks[index - 1].end_offset == chunk.start_offset


def test_negative_offsets_and_continuation():
    stored = StoredToolContent("c", "s", "0123456789")
    builder = CachedToolOutputWindowBuilder(char_budget=3)
    first = builder.build_range_window(stored, start=1, end=-1)
    second = builder.build_range_window(stored, start=first.end_offset, end=-1)
    assert first.text == "123"
    assert first.truncated is True
    assert second.text == "456"
    assert second.start_offset == 4
