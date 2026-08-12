"""Mongo Entity 到领域事实的反序列化。"""

from rag.domain.content_revision import ContentRevision, SourcePart
from rag.domain.document_structure import PageRange, Section, StructureMode
from rag.domain.entities import (
    ContentRevisionEntity,
    ReadingBlockEntity,
    SectionEntity,
    SourcePartEntity,
    SourceRefEntity,
)
from rag.domain.reading import ReadingBlock
from rag.domain.retrieval import SourceRef
from rag.utils.chunkers import SourceSpan


def to_content_revision(record: ContentRevisionEntity) -> ContentRevision:
    return ContentRevision(
        resource_id=record.resource_id,
        content_revision=record.content_revision,
        document_version=record.document_version,
        content_hash=record.content_hash,
        index_schema_version=record.index_schema_version,
        structure_mode=StructureMode(record.structure_mode),
        total_length=record.total_length,
        pages=[
            PageRange(
                page_index=page.page_index,
                page_label=page.page_label,
                source_span=SourceSpan(page.start_offset, page.end_offset),
            )
            for page in record.pages
        ],
    )


def to_source_part(record: SourcePartEntity) -> SourcePart:
    return SourcePart(
        resource_id=record.resource_id,
        content_revision=record.content_revision,
        part_index=record.part_index,
        source_span=SourceSpan(record.start_offset, record.end_offset),
        text=record.text,
    )


def to_section(record: SectionEntity) -> Section:
    return Section(
        section_id=record.section_id,
        title=record.title,
        level=record.level,
        parent_section_id=record.parent_section_id,
        ordinal=record.ordinal,
        section_path=list(record.section_path),
        own_span=SourceSpan(record.own_start, record.own_end),
        subtree_span=SourceSpan(record.own_start, record.subtree_end),
        preview=record.preview,
    )


def to_reading_block(record: ReadingBlockEntity) -> ReadingBlock:
    return ReadingBlock(
        block_id=record.block_id,
        section_id=record.section_id,
        ordinal=record.ordinal,
        raw_text=record.raw_text,
        source_spans=[
            SourceSpan(span.start_offset, span.end_offset)
            for span in record.source_spans
        ],
        page_labels=list(record.page_labels),
        anchor_labels=list(record.anchor_labels),
    )


def to_source_ref(record: SourceRefEntity) -> SourceRef:
    return SourceRef(
        ref_id=record.ref_id,
        resource_id=record.resource_id,
        content_revision=record.content_revision,
        chunk_id=record.chunk_id,
        reading_block_id=record.reading_block_id,
        section_id=record.section_id,
        section_path=list(record.section_path),
        source_spans=[
            SourceSpan(span.start_offset, span.end_offset)
            for span in record.source_spans
        ],
        page_labels=list(record.page_labels),
        anchor_labels=list(record.anchor_labels),
    )
