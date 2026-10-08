from chat.application.tools.core.output_cache.cache_store import (
    StoredToolContent,
    _build_cache_chunks,
)
from chat.application.tools.session_tools.cached_tool_output_tools.read_by_section import (
    _read_by_section,
)
from chat.application.tools.session_tools.cached_tool_output_tools.window import (
    CachedToolOutputWindowBuilder,
)
from common.utils.markdown import DocumentChunker, TiktokenTokenCounter
from pydantic import TypeAdapter


def test_cache_keeps_ignored_preamble_and_serializes_exact_spans():
    text = "<!-- ignored by parser -->\n\n# Heading\n\nbody\n"
    result = DocumentChunker().chunk(text)
    chunks = _build_cache_chunks(
        text, result.sections, result.anchors, TiktokenTokenCounter()
    )
    assert "".join(chunk.text for chunk in chunks) == text
    stored = StoredToolContent("c", "s", text, chunks, result.sections, result.anchors)
    adapter = TypeAdapter(StoredToolContent)
    assert adapter.validate_json(adapter.dump_json(stored)) == stored


def test_section_read_retains_section_provenance():
    text = "# Heading\n\nbody🙂\n\n## Nested\n\nchild body\n"
    result = DocumentChunker().chunk(text)
    stored = StoredToolContent("c", "s", text, sections=result.sections)
    section = result.sections[0]
    read = _read_by_section(
        content_id="c",
        section_ids=[section.section_id],
        sections=result.sections,
        builder=CachedToolOutputWindowBuilder(char_budget=100),
        stored=stored,
    )
    assert read.section_contents[0].window.text == "body🙂\n"
    assert "child body" not in read.section_contents[0].window.text
