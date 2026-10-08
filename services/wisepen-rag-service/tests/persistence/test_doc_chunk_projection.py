from common.utils.markdown import DocumentChunker
from pydantic import TypeAdapter

from rag.application.document.models import DocChunk
from rag.application.plugins.core.metadata import DocChunkMetadataCodec
from rag.core.persistence.mongo.doc_chunk_repository import _to_document, _to_domain
from rag.core.persistence.qdrant.document_vector_repository import _to_point
from rag.domain.acl import ResourceAcl
from rag.domain.entities.doc_chunks import DocChunkEntity


def _chunk():
    source = DocumentChunker().chunk("# A\n\n中文正文\n").chunks[0]
    return DocChunk(
        chunk_id="chunk",
        resource_id="r",
        content_revision="rev",
        section_id="sec",
        section_path=["A"],
        chunk_index=0,
        raw_text=source.text,
        node_ids=list(source.node_ids),
        content_token_count=source.content_token_count,
    )


def test_mongo_round_trip_does_not_include_chunk_spans():
    chunk = _chunk()
    codec = DocChunkMetadataCodec()
    payload = _to_document(chunk, codec)
    assert "source_spans" not in payload
    # Beanie's database-bound constructor is irrelevant for schema projection;
    # construct the validated persistence shape without initializing a database.
    entity = DocChunkEntity.model_construct(**payload)
    assert _to_domain(entity, codec) == chunk
    restored = TypeAdapter(DocChunk).validate_json(
        TypeAdapter(DocChunk).dump_json(chunk)
    )
    assert restored.node_ids == chunk.node_ids
    assert restored.content_token_count == chunk.content_token_count


def test_qdrant_payload_uses_node_order_and_token_identity():
    chunk = _chunk()
    point = _to_point(
        chunk=chunk,
        dense_vector=[1.0, 0.0, 0.0],
        resource_acl=ResourceAcl("r", 1, "owner"),
        dense_vector_name="dense",
        sparse_vector_name="sparse",
        filter_values={},
    )
    assert point.payload["node_ids"] == chunk.node_ids
    assert point.payload["chunk_index"] == chunk.chunk_index
    assert point.payload["content_token_count"] == chunk.content_token_count
    assert "source_spans" not in point.payload
