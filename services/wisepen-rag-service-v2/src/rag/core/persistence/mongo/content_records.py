"""Mongo 内容记录与领域事实之间的字段转换。"""

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


def section_document(
    revision: ContentRevision,
    section: Section,
) -> dict[str, object]:
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
    return {
        "start_offset": span.start_offset,
        "end_offset": span.end_offset,
    }


def to_content_revision(document: dict[str, object]) -> ContentRevision:
    return ContentRevision(
        resource_id=str(document["resource_id"]),
        content_revision=str(document["content_revision"]),
        document_version=int(document["document_version"]),
        content_hash=str(document["content_hash"]),
        index_schema_version=str(document["index_schema_version"]),
        structure_mode=StructureMode(str(document["structure_mode"])),
        total_length=int(document["total_length"]),
        pages=[
            PageRange(
                page_index=int(page["page_index"]),
                page_label=str(page["page_label"]),
                source_span=SourceSpan(
                    int(page["start_offset"]),
                    int(page["end_offset"]),
                ),
            )
            for page in document.get("pages", [])
        ],
    )


def to_section(document: dict[str, object]) -> Section:
    return Section(
        section_id=str(document["section_id"]),
        title=str(document["title"]),
        level=int(document["level"]),
        parent_section_id=(
            str(document["parent_section_id"])
            if document.get("parent_section_id") is not None
            else None
        ),
        ordinal=int(document["ordinal"]),
        section_path=[str(value) for value in document.get("section_path", [])],
        own_span=SourceSpan(
            int(document["own_start"]),
            int(document["own_end"]),
        ),
        subtree_span=SourceSpan(
            int(document["own_start"]),
            int(document["subtree_end"]),
        ),
        preview=str(document.get("preview", "")),
    )


def to_reading_block(document: dict[str, object]) -> ReadingBlock:
    return ReadingBlock(
        block_id=str(document["block_id"]),
        section_id=str(document["section_id"]),
        ordinal=int(document["ordinal"]),
        raw_text=str(document["raw_text"]),
        source_spans=to_source_spans(document.get("source_spans", [])),
        page_labels=[str(value) for value in document.get("page_labels", [])],
        anchor_labels=[str(value) for value in document.get("anchor_labels", [])],
    )


def to_source_ref(document: dict[str, object]) -> SourceRef:
    return SourceRef(
        ref_id=str(document["ref_id"]),
        resource_id=str(document["resource_id"]),
        content_revision=str(document["content_revision"]),
        chunk_id=str(document["chunk_id"]),
        reading_block_id=str(document["reading_block_id"]),
        section_id=str(document["section_id"]),
        section_path=[str(value) for value in document.get("section_path", [])],
        source_spans=to_source_spans(document.get("source_spans", [])),
        page_labels=[str(value) for value in document.get("page_labels", [])],
        anchor_labels=[str(value) for value in document.get("anchor_labels", [])],
    )


def to_source_spans(documents: object) -> list[SourceSpan]:
    if not isinstance(documents, list):
        raise TypeError("stored source spans must be a list")
    return [
        SourceSpan(
            int(document["start_offset"]),
            int(document["end_offset"]),
        )
        for document in documents
    ]


def read_source_spans(
    *,
    content_revision: str,
    documents: list[dict[str, object]],
    source_spans: Sequence[SourceSpan],
) -> str:
    fragments: list[str] = []
    for span in source_spans:
        cursor = span.start_offset
        span_fragments: list[str] = []
        for document in documents:
            start_offset = int(document["start_offset"])
            end_offset = int(document["end_offset"])
            text = str(document["text"])
            if end_offset - start_offset != len(text):
                raise RuntimeError(
                    f"content revision {content_revision} has an invalid source part"
                )
            if end_offset <= cursor:
                continue
            if start_offset >= span.end_offset:
                break
            if start_offset > cursor:
                raise RuntimeError(
                    f"content revision {content_revision} source parts have a gap"
                )

            fragment_end = min(end_offset, span.end_offset)
            span_fragments.append(
                text[cursor - start_offset : fragment_end - start_offset]
            )
            cursor = fragment_end
            if cursor == span.end_offset:
                break
        if cursor != span.end_offset:
            raise RuntimeError(
                f"content revision {content_revision} source parts do not cover span"
            )
        fragments.append("".join(span_fragments))
    return "\n\n".join(fragments)
