from rag.application.document.context import build_graph_extraction_context
from rag.application.document.models import ContentRevision, DocChunk


def _chunk() -> DocChunk:
    revision = ContentRevision.create(
        resource_id="resource-1",
        document_version=1,
        raw_content="target",
    )
    return DocChunk(
        chunk_id="chunk-1",
        resource_id="resource-1",
        content_revision=revision.content_revision,
        section_id="section-1",
        section_path=["标题", "子节"],
        chunk_index=0,
        raw_text="target evidence",
        node_ids=["node-1"],
        content_token_count=3,
    )


def test_graph_context_separates_section_background_and_target_evidence() -> None:
    context = build_graph_extraction_context(_chunk())

    assert "<section_path>" in context
    assert "标题 > 子节" in context
    assert '<target_chunk id="chunk-1">' in context
    assert "target evidence" in context
    assert context.index("<section_path>") < context.index("<target_chunk")


def test_doc_chunk_does_not_require_source_spans() -> None:
    chunk = _chunk()
    assert chunk.node_ids == ["node-1"]
    assert chunk.content_token_count == 3
    assert not hasattr(chunk, "chunk_span")
