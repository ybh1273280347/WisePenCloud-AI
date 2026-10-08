from common.utils.markdown import DocumentChunker

from rag.application.document.models import rag_section_id
from rag.application.document.preparation import _to_doc_chunk


def test_common_to_rag_uses_structural_identity_and_tokens():
    result = DocumentChunker().chunk("# 章节\n\n正文 中文🙂\n")
    section_ids = {
        section.section_id: rag_section_id(
            resource_id="r",
            content_revision="rev",
            common_section_id=section.section_id,
        )
        for section in result.sections
    }
    sections = {section_ids[section.section_id]: section for section in result.sections}
    chunk = _to_doc_chunk(
        result.chunks[0],
        resource_id="r",
        content_revision="rev",
        section_ids=section_ids,
        sections_by_id=sections,
    )
    assert chunk.node_ids == list(result.chunks[0].node_ids)
    assert chunk.section_path == ["章节"]
    assert chunk.content_token_count == result.chunks[0].content_token_count
    assert chunk.chunk_index == 0
    assert not hasattr(chunk, "source_spans")
