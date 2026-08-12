"""领域事实与 Mongo 字段之间的纯结构映射。"""

from collections.abc import Sequence

from rag.domain.content_revision import ContentRevision, SourcePart
from rag.domain.document_structure import PageRange, Section, StructureMode
from rag.domain.reading import ReadingBlock
from rag.domain.retrieval import SourceRef
from rag.utils.chunkers import SourceSpan


def revision_document(revision: ContentRevision) -> dict[str, object]:
    return {
        "resource_id": revision.resource_id,
        "content_revision": revision.content_revision,
        "document_version": revision.document_version,
        "content_hash": revision.content_hash,
        "index_schema_version": revision.index_schema_version,
        "structure_mode": revision.structure_mode.value,
        "total_length": revision.total_length,
        "pages": [
            {
                "page_index": page.page_index,
                "page_label": page.page_label,
                "start_offset": page.source_span.start_offset,
                "end_offset": page.source_span.end_offset,
            }
            for page in revision.pages
        ],
    }


def source_part_document(part: SourcePart) -> dict[str, object]:
    return {
        "resource_id": part.resource_id,
        "content_revision": part.content_revision,
        "part_index": part.part_index,
        "start_offset": part.source_span.start_offset,
        "end_offset": part.source_span.end_offset,
        "text": part.text,
    }


def section_document(revision: ContentRevision, section: Section) -> dict[str, object]:
    return {
        "resource_id": revision.resource_id,
        "content_revision": revision.content_revision,
        "section_id": section.section_id,
        "title": section.title,
        "level": section.level,
        "parent_section_id": section.parent_section_id,
        "ordinal": section.ordinal,
        "section_path": list(section.section_path),
        "preview": section.preview,
        "own_start": section.own_span.start_offset,
        "own_end": section.own_span.end_offset,
        "subtree_end": section.subtree_span.end_offset,
    }


def reading_block_document(
    revision: ContentRevision,
    block: ReadingBlock,
) -> dict[str, object]:
    return {
        "resource_id": revision.resource_id,
        "content_revision": revision.content_revision,
        "block_id": block.block_id,
        "section_id": block.section_id,
        "ordinal": block.ordinal,
        "raw_text": block.raw_text,
        "source_spans": [span_document(span) for span in block.source_spans],
        "start_offset": block.source_spans[0].start_offset,
        "end_offset": block.source_spans[-1].end_offset,
        "page_labels": list(block.page_labels),
        "anchor_labels": list(block.anchor_labels),
    }


def source_ref_document(
    revision: ContentRevision,
    source_ref: SourceRef,
) -> dict[str, object]:
    return {
        "resource_id": revision.resource_id,
        "content_revision": revision.content_revision,
        "ref_id": source_ref.ref_id,
        "chunk_id": source_ref.chunk_id,
        "reading_block_id": source_ref.reading_block_id,
        "section_id": source_ref.section_id,
        "section_path": list(source_ref.section_path),
        "source_spans": [span_document(span) for span in source_ref.source_spans],
        "page_labels": list(source_ref.page_labels),
        "anchor_labels": list(source_ref.anchor_labels),
    }


def span_document(span: SourceSpan) -> dict[str, int]:
    return {"start_offset": span.start_offset, "end_offset": span.end_offset}


def to_content_revision(record: object) -> ContentRevision:
    return ContentRevision(
        resource_id=str(record.resource_id),
        content_revision=str(record.content_revision),
        document_version=int(record.document_version),
        content_hash=str(record.content_hash),
        index_schema_version=str(record.index_schema_version),
        structure_mode=StructureMode(str(record.structure_mode)),
        total_length=int(record.total_length),
        pages=[
            PageRange(
                page_index=int(page.page_index),
                page_label=str(page.page_label),
                source_span=SourceSpan(
                    int(page.start_offset),
                    int(page.end_offset),
                ),
            )
            for page in record.pages
        ],
    )


def to_source_part(record: object) -> SourcePart:
    return SourcePart(
        resource_id=str(record.resource_id),
        content_revision=str(record.content_revision),
        part_index=int(record.part_index),
        source_span=SourceSpan(int(record.start_offset), int(record.end_offset)),
        text=str(record.text),
    )


def to_section(record: object) -> Section:
    return Section(
        section_id=str(record.section_id),
        title=str(record.title),
        level=int(record.level),
        parent_section_id=(
            str(record.parent_section_id)
            if record.parent_section_id is not None
            else None
        ),
        ordinal=int(record.ordinal),
        section_path=[str(value) for value in record.section_path],
        own_span=SourceSpan(int(record.own_start), int(record.own_end)),
        subtree_span=SourceSpan(int(record.own_start), int(record.subtree_end)),
        preview=str(record.preview),
    )


def to_reading_block(record: object) -> ReadingBlock:
    return ReadingBlock(
        block_id=str(record.block_id),
        section_id=str(record.section_id),
        ordinal=int(record.ordinal),
        raw_text=str(record.raw_text),
        source_spans=to_source_spans(record.source_spans),
        page_labels=[str(value) for value in record.page_labels],
        anchor_labels=[str(value) for value in record.anchor_labels],
    )


def to_source_ref(record: object) -> SourceRef:
    return SourceRef(
        ref_id=str(record.ref_id),
        resource_id=str(record.resource_id),
        content_revision=str(record.content_revision),
        chunk_id=str(record.chunk_id),
        reading_block_id=str(record.reading_block_id),
        section_id=str(record.section_id),
        section_path=[str(value) for value in record.section_path],
        source_spans=to_source_spans(record.source_spans),
        page_labels=[str(value) for value in record.page_labels],
        anchor_labels=[str(value) for value in record.anchor_labels],
    )


def to_source_spans(records: Sequence[object]) -> list[SourceSpan]:
    return [
        SourceSpan(int(record.start_offset), int(record.end_offset))
        for record in records
    ]
