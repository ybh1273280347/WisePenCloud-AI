"""从 ReadingBlock 构建检索评分使用的 RetrievalChunk。"""

from hashlib import sha256

from rag.domain.models.structure import DocumentStructure, Section, StructureMode
from rag.domain.models.content import ReadingBlock
from rag.domain.models.retrieval import RetrievalChunk
from rag.utils.chunkers import (
    ChunkDocument,
    MarkdownChunker,
    PlainTextChunker,
    PlainTextChunkerConfig,
    SourceSpan,
)

from ._source_spans import _map_rendered_spans_to_source, _overlaps, _render_source_text
from .reading_blocks import _build_reading_block_id

_RETRIEVAL_CHUNK_MAX_CHARACTERS = 800
_FLAT_TEXT_CHUNK_OVERLAP = 100


def build_retrieval_chunks(
    *,
    resource_id: str,
    content_revision: str,
    markdown: str,
    structure: DocumentStructure,
    sections: list[Section],
    reading_blocks: list[ReadingBlock],
) -> list[RetrievalChunk]:
    """校验 ReadingBlock 后生成用于评分的确定性子块。"""
    sections_by_id = _validate_reading_blocks(
        resource_id=resource_id,
        content_revision=content_revision,
        markdown=markdown,
        structure=structure,
        sections=sections,
        reading_blocks=reading_blocks,
    )
    chunker = (
        PlainTextChunker(
            PlainTextChunkerConfig(
                chunk_size=_RETRIEVAL_CHUNK_MAX_CHARACTERS,
                chunk_overlap=_FLAT_TEXT_CHUNK_OVERLAP,
            )
        )
        if structure.mode is StructureMode.FLAT_TEXT
        else MarkdownChunker(max_characters=_RETRIEVAL_CHUNK_MAX_CHARACTERS)
    )
    chunks: list[RetrievalChunk] = []

    for reading_block in reading_blocks:
        section = sections_by_id[reading_block.section_id]
        result = chunker.chunk(
            document=ChunkDocument(
                text=reading_block.raw_text,
                document_id=reading_block.block_id,
                content_type=(
                    "text/plain"
                    if structure.mode is StructureMode.FLAT_TEXT
                    else "text/markdown"
                ),
            )
        )
        for chunk in result.chunks:
            source_spans = _map_rendered_spans_to_source(
                local_spans=list(chunk.source_spans),
                source_spans=reading_block.source_spans,
            )
            if not source_spans:
                raise ValueError(
                    f"retrieval chunk from {reading_block.block_id} has no source span"
                )
            raw_text = _render_source_text(markdown, source_spans)
            chunks.append(
                RetrievalChunk(
                    chunk_id=_build_retrieval_chunk_id(
                        reading_block_id=reading_block.block_id,
                        source_spans=source_spans,
                    ),
                    reading_block_id=reading_block.block_id,
                    section_id=section.section_id,
                    section_path=list(section.section_path),
                    raw_text=raw_text,
                    index_text=raw_text,
                    source_spans=source_spans,
                    page_labels=[
                        page.page_label
                        for page in structure.pages
                        if _overlaps(page.source_span, source_spans)
                    ],
                    anchor_labels=[
                        anchor.label
                        for anchor in structure.anchors
                        if _overlaps(anchor.source_span, source_spans)
                    ],
                )
            )

    if len({chunk.chunk_id for chunk in chunks}) != len(chunks):
        raise ValueError("retrieval chunk identities are not unique")
    return chunks


def _build_retrieval_chunk_id(
    *,
    reading_block_id: str,
    source_spans: list[SourceSpan],
) -> str:
    span_identity = ";".join(
        f"{span.start_offset}:{span.end_offset}" for span in source_spans
    )
    identity = f"{reading_block_id}\0{span_identity}"
    return f"rrc_{sha256(identity.encode('utf-8')).hexdigest()[:32]}"


def _validate_reading_blocks(
    *,
    resource_id: str,
    content_revision: str,
    markdown: str,
    structure: DocumentStructure,
    sections: list[Section],
    reading_blocks: list[ReadingBlock],
) -> dict[str, Section]:
    if structure.total_length != len(markdown):
        raise ValueError("document structure length does not match markdown")
    sections_by_id = {section.section_id: section for section in sections}
    if len(sections_by_id) != len(sections):
        raise ValueError("section identities are not unique")
    if structure.mode is StructureMode.EMPTY and reading_blocks:
        raise ValueError("empty document must not contain reading blocks")

    blocks_by_section: dict[str, list[ReadingBlock]] = {}
    seen_block_ids: set[str] = set()
    for block in reading_blocks:
        if block.block_id in seen_block_ids:
            raise ValueError("reading block identities are not unique")
        seen_block_ids.add(block.block_id)
        section = sections_by_id.get(block.section_id)
        if section is None:
            raise ValueError(f"reading block {block.block_id} has no section")
        if not block.source_spans:
            raise ValueError(f"reading block {block.block_id} has no source span")
        if any(span.start_offset == span.end_offset for span in block.source_spans):
            raise ValueError(f"reading block {block.block_id} has an empty source span")
        if any(
            span.start_offset < section.own_span.start_offset
            or span.end_offset > section.own_span.end_offset
            for span in block.source_spans
        ):
            raise ValueError(f"reading block {block.block_id} exceeds its section")
        if any(
            left.end_offset > right.start_offset
            for left, right in zip(
                block.source_spans,
                block.source_spans[1:],
                strict=False,
            )
        ):
            raise ValueError(f"reading block {block.block_id} has overlapping spans")
        if block.raw_text != _render_source_text(markdown, block.source_spans):
            raise ValueError(
                f"reading block {block.block_id} does not match authoritative source"
            )
        expected_block_id = _build_reading_block_id(
            resource_id=resource_id,
            content_revision=content_revision,
            section_id=section.section_id,
            source_spans=block.source_spans,
        )
        if block.block_id != expected_block_id:
            raise ValueError("reading block identity does not match its ownership")
        blocks_by_section.setdefault(section.section_id, []).append(block)

    for section_id, section_blocks in blocks_by_section.items():
        if [block.ordinal for block in section_blocks] != list(
            range(len(section_blocks))
        ):
            raise ValueError(f"section {section_id} has invalid reading block ordinals")
    return sections_by_id
