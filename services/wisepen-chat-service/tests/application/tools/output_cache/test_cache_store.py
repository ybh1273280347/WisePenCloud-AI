import json

from common.utils.markdown import MarkdownChunker
from pydantic import TypeAdapter

from chat.application.tools.core.output_cache.cache_store import StoredToolContent
from chat.application.tools.session_tools.cached_tool_output_tools.read_by_range import (
    _normalize_offset,
)
from chat.application.tools.session_tools.cached_tool_output_tools.read_by_section import (
    _read_by_section,
)


def test_stored_content_round_trips_and_ignores_old_chunk_index_field():
    text = "<!-- ignored by parser -->\n\n# Heading\n\nbody\n"
    result = MarkdownChunker().chunk(text)
    stored = StoredToolContent(
        content_id="c",
        session_id="s",
        text=text,
        sections=result.sections,
        anchors=result.anchors,
    )
    adapter = TypeAdapter(StoredToolContent)
    decoded = json.loads(adapter.dump_json(stored))
    decoded["chunks"] = [{"old": "index data"}]

    assert adapter.validate_json(json.dumps(decoded)) == stored
    assert not hasattr(stored, "chunks")


def test_section_reader_uses_own_and_subtree_source_spans_and_pages():
    text = "# Heading\n\nbody12345\n\n## Nested\n\nchild body\n"
    result = MarkdownChunker().chunk(text)
    stored = StoredToolContent("c", "s", text, sections=result.sections)
    section = result.sections[0]

    first_page = _read_by_section(
        content_id="c",
        section_id=section.section_id,
        scope="own",
        offset=0,
        sections=result.sections,
        stored=stored,
        char_budget=8,
    )
    last_offset = (section.own_span.length - 1) // 8
    last_page = _read_by_section(
        content_id="c",
        section_id=section.section_id,
        scope="own",
        offset=last_offset,
        sections=result.sections,
        stored=stored,
        char_budget=8,
    )
    beyond_page = _read_by_section(
        content_id="c",
        section_id=section.section_id,
        scope="own",
        offset=999,
        sections=result.sections,
        stored=stored,
        char_budget=8,
    )
    subtree = _read_by_section(
        content_id="c",
        section_id=section.section_id,
        scope="subtree",
        offset=0,
        sections=result.sections,
        stored=stored,
        char_budget=len(text),
    )

    assert first_page.text == text[section.own_span.start_offset : 8]
    assert first_page.has_more is True
    last_start = section.own_span.start_offset + last_offset * 8
    assert last_page.text == text[last_start : section.own_span.end_offset]
    assert last_page.has_more is False
    assert beyond_page.text == ""
    assert beyond_page.has_more is False
    assert "child body" in subtree.text


def test_range_offset_normalization_keeps_python_negative_index_semantics():
    assert _normalize_offset(-3, 10, default=0) == 7
    assert _normalize_offset(100_000_000, 10, default=0) == 10
