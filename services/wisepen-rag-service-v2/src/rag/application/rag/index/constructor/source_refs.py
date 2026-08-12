"""构建 RetrievalChunk 到权威原文的 SourceRef。"""

from hashlib import sha256

from rag.domain.models.content import ReadingBlock
from rag.domain.models.retrieval import RetrievalChunk, SourceRef
from rag.domain.models.structure import DocumentStructure, Section

from ._source_spans import _overlaps, _render_source_text
from .retrieval_chunks import _build_retrieval_chunk_id


def build_source_refs(
    *,
    resource_id: str,
    content_revision: str,
    markdown: str,
    structure: DocumentStructure,
    sections: list[Section],
    reading_blocks: list[ReadingBlock],
    retrieval_chunks: list[RetrievalChunk],
) -> list[SourceRef]:
    """固化 chunk、ReadingBlock、Section 与权威原文的完整归属链。"""
    if structure.total_length != len(markdown):
        raise ValueError("document structure length does not match markdown")
    sections_by_id = {section.section_id: section for section in sections}
    if len(sections_by_id) != len(sections):
        raise ValueError("section identities are not unique")
    blocks_by_id = {block.block_id: block for block in reading_blocks}
    if len(blocks_by_id) != len(reading_blocks):
        raise ValueError("reading block identities are not unique")

    refs: list[SourceRef] = []
    for chunk in retrieval_chunks:
        if not chunk.source_spans:
            raise ValueError(f"retrieval chunk {chunk.chunk_id} has no source span")
        if any(span.start_offset == span.end_offset for span in chunk.source_spans):
            raise ValueError(
                f"retrieval chunk {chunk.chunk_id} has an empty source span"
            )
        block = blocks_by_id.get(chunk.reading_block_id)
        if block is None:
            raise ValueError(f"retrieval chunk {chunk.chunk_id} has no reading block")
        section = sections_by_id.get(chunk.section_id)
        if section is None or block.section_id != section.section_id:
            raise ValueError(
                f"retrieval chunk {chunk.chunk_id} has an invalid section owner"
            )
        if chunk.section_path != section.section_path:
            raise ValueError(
                f"retrieval chunk {chunk.chunk_id} has an invalid section path"
            )
        if any(
            not any(
                block_span.start_offset <= chunk_span.start_offset
                and chunk_span.end_offset <= block_span.end_offset
                for block_span in block.source_spans
            )
            for chunk_span in chunk.source_spans
        ):
            raise ValueError(
                f"retrieval chunk {chunk.chunk_id} exceeds its reading block"
            )
        if chunk.raw_text != _render_source_text(markdown, chunk.source_spans):
            raise ValueError(
                f"retrieval chunk {chunk.chunk_id} does not match authoritative source"
            )
        expected_page_labels = [
            page.page_label
            for page in structure.pages
            if _overlaps(page.source_span, chunk.source_spans)
        ]
        if chunk.page_labels != expected_page_labels:
            raise ValueError(
                f"retrieval chunk {chunk.chunk_id} has invalid page labels"
            )
        expected_anchor_labels = [
            anchor.label
            for anchor in structure.anchors
            if _overlaps(anchor.source_span, chunk.source_spans)
        ]
        if chunk.anchor_labels != expected_anchor_labels:
            raise ValueError(
                f"retrieval chunk {chunk.chunk_id} has invalid anchor labels"
            )
        expected_chunk_id = _build_retrieval_chunk_id(
            reading_block_id=block.block_id,
            source_spans=chunk.source_spans,
        )
        if chunk.chunk_id != expected_chunk_id:
            raise ValueError("retrieval chunk identity does not match its ownership")

        refs.append(
            SourceRef(
                ref_id=_build_source_ref_id(
                    resource_id=resource_id,
                    content_revision=content_revision,
                    chunk=chunk,
                ),
                resource_id=resource_id,
                content_revision=content_revision,
                chunk_id=chunk.chunk_id,
                reading_block_id=block.block_id,
                section_id=section.section_id,
                section_path=list(section.section_path),
                source_spans=list(chunk.source_spans),
                page_labels=list(chunk.page_labels),
                anchor_labels=list(chunk.anchor_labels),
            )
        )

    if len({ref.ref_id for ref in refs}) != len(refs):
        raise ValueError("source ref identities are not unique")
    return refs


def _build_source_ref_id(
    *,
    resource_id: str,
    content_revision: str,
    chunk: RetrievalChunk,
) -> str:
    identity = (
        f"{resource_id}\0{content_revision}\0{chunk.chunk_id}"
        f"\0{chunk.reading_block_id}\0{chunk.section_id}"
    )
    return f"rsrc_{sha256(identity.encode('utf-8')).hexdigest()[:32]}"
