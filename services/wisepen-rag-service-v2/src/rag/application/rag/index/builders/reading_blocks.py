"""从文档结构构建稳定、可回源的 ReadingBlock。"""

from collections.abc import Sequence
from hashlib import sha256

from rag.domain.models.structure import DocumentStructure, Section, StructureMode
from rag.domain.models.content import ReadingBlock
from rag.utils.chunkers import (
    BlockKind,
    ChunkDocument,
    MarkdownChunker,
    PlainTextChunker,
    PlainTextChunkerConfig,
    SourceSpan,
    TextBlock,
)
from rag.utils.chunkers.markdown import MarkdownParser

from .structure import build_section_id

_READING_BLOCK_MAX_CHARACTERS = 4000


def build_flat_text_sections(
    *,
    resource_id: str,
    content_revision: str,
    markdown: str,
) -> list[Section]:
    """把无标题正文按 4000 个可见字符拆成无重叠导航 Section。"""
    span_groups = _split_flat_text_source_spans(markdown)
    sections: list[Section] = []

    for index, source_spans in enumerate(span_groups):
        own_span = SourceSpan(
            source_spans[0].start_offset,
            source_spans[-1].end_offset,
        )
        title = f"全文片段 {index + 1}"
        sections.append(
            Section(
                section_id=build_section_id(
                    resource_id=resource_id,
                    content_revision=content_revision,
                    kind="flat_text",
                    start_offset=own_span.start_offset,
                    end_offset=own_span.end_offset,
                ),
                title=title,
                level=1,
                parent_section_id=None,
                ordinal=index,
                section_path=[title],
                own_span=own_span,
                subtree_span=own_span,
            )
        )

    return sections


def build_reading_blocks(
    *,
    resource_id: str,
    content_revision: str,
    markdown: str,
    structure: DocumentStructure,
    sections: list[Section],
) -> list[ReadingBlock]:
    """按结构模式生成 ReadingBlock；empty 文档不产生伪正文块。"""
    if structure.total_length != len(markdown):
        raise ValueError("document structure length does not match markdown")
    if structure.mode is StructureMode.EMPTY:
        if sections:
            raise ValueError("empty document must not contain sections")
        return []
    if structure.mode is StructureMode.FLAT_TEXT:
        blocks = _build_flat_text_reading_blocks(
            resource_id=resource_id,
            content_revision=content_revision,
            markdown=markdown,
            structure=structure,
            sections=sections,
        )
    else:
        blocks = _build_section_reading_blocks(
            resource_id=resource_id,
            content_revision=content_revision,
            markdown=markdown,
            structure=structure,
            sections=sections,
        )

    blocks_by_section: dict[str, list[ReadingBlock]] = {}
    for block in blocks:
        blocks_by_section.setdefault(block.section_id, []).append(block)
    for section in sections:
        section.preview = " ".join(
            block.raw_text for block in blocks_by_section.get(section.section_id, [])
        ).replace("\n", " ")[:500]
    return blocks


def _build_section_reading_blocks(
    *,
    resource_id: str,
    content_revision: str,
    markdown: str,
    structure: DocumentStructure,
    sections: list[Section],
) -> list[ReadingBlock]:
    blocks: list[ReadingBlock] = []
    chunker = MarkdownChunker(max_characters=_READING_BLOCK_MAX_CHARACTERS)

    for section in sections:
        if section.own_span.end_offset > len(markdown):
            raise ValueError(f"section {section.section_id} exceeds markdown bounds")
        if section.own_span.start_offset == section.own_span.end_offset:
            continue

        section_text = markdown[
            section.own_span.start_offset : section.own_span.end_offset
        ]
        result = chunker.chunk(
            document=ChunkDocument(
                text=section_text,
                document_id=section.section_id,
                content_type="text/markdown",
            )
        )
        heading_end = _heading_end_offset(result.blocks, section)
        ordinal = 0

        for chunk in result.chunks:
            source_spans = [
                SourceSpan(
                    section.own_span.start_offset + span.start_offset,
                    section.own_span.start_offset + span.end_offset,
                )
                for span in chunk.source_spans
                if span.end_offset > heading_end
            ]
            if not source_spans:
                continue
            blocks.append(
                _reading_block(
                    resource_id=resource_id,
                    content_revision=content_revision,
                    markdown=markdown,
                    section=section,
                    ordinal=ordinal,
                    source_spans=source_spans,
                    structure=structure,
                )
            )
            ordinal += 1

    return blocks


def _build_flat_text_reading_blocks(
    *,
    resource_id: str,
    content_revision: str,
    markdown: str,
    structure: DocumentStructure,
    sections: list[Section],
) -> list[ReadingBlock]:
    span_groups = _split_flat_text_source_spans(markdown)
    if len(sections) != len(span_groups):
        raise ValueError("flat text sections do not match reading block boundaries")

    blocks: list[ReadingBlock] = []
    for section, source_spans in zip(sections, span_groups, strict=True):
        expected_section_id = build_section_id(
            resource_id=resource_id,
            content_revision=content_revision,
            kind="flat_text",
            start_offset=source_spans[0].start_offset,
            end_offset=source_spans[-1].end_offset,
        )
        if section.section_id != expected_section_id:
            raise ValueError(
                "flat text section identity does not match its source span"
            )
        blocks.append(
            _reading_block(
                resource_id=resource_id,
                content_revision=content_revision,
                markdown=markdown,
                section=section,
                ordinal=0,
                source_spans=source_spans,
                structure=structure,
            )
        )
    return blocks


def _split_flat_text_source_spans(markdown: str) -> list[list[SourceSpan]]:
    parsed_blocks = MarkdownParser().parse(markdown)
    effective_spans = [
        SourceSpan(block.start_offset, block.end_offset)
        for block in parsed_blocks
        if block.block_kind is not BlockKind.PAGE_MARKER
        and block.text.strip()
        and block.start_offset is not None
        and block.end_offset is not None
    ]
    if not effective_spans:
        return []

    rendered_text = render_source_text(markdown, effective_spans)
    chunks = (
        PlainTextChunker(
            PlainTextChunkerConfig(
                chunk_size=_READING_BLOCK_MAX_CHARACTERS,
                chunk_overlap=0,
            )
        )
        .chunk(document=ChunkDocument(text=rendered_text))
        .chunks
    )

    return [
        map_rendered_spans_to_source(
            local_spans=list(chunk.source_spans),
            source_spans=effective_spans,
        )
        for chunk in chunks
    ]


def _heading_end_offset(
    parsed_blocks: Sequence[TextBlock],
    section: Section,
) -> int:
    if section.level == 0:
        return 0
    first_block = parsed_blocks[0] if parsed_blocks else None
    if first_block is None or first_block.block_kind is not BlockKind.HEADING:
        raise ValueError(
            f"section {section.section_id} does not start with its heading"
        )
    if first_block.end_offset is None:
        raise ValueError(f"section {section.section_id} heading has no source offset")
    return first_block.end_offset


def _reading_block(
    *,
    resource_id: str,
    content_revision: str,
    markdown: str,
    section: Section,
    ordinal: int,
    source_spans: list[SourceSpan],
    structure: DocumentStructure,
) -> ReadingBlock:
    return ReadingBlock(
        block_id=build_reading_block_id(
            resource_id=resource_id,
            content_revision=content_revision,
            section_id=section.section_id,
            source_spans=source_spans,
        ),
        section_id=section.section_id,
        ordinal=ordinal,
        raw_text=render_source_text(markdown, source_spans),
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


def build_reading_block_id(
    *,
    resource_id: str,
    content_revision: str,
    section_id: str,
    source_spans: list[SourceSpan],
) -> str:
    span_identity = ";".join(
        f"{span.start_offset}:{span.end_offset}" for span in source_spans
    )
    identity = f"{resource_id}\0{content_revision}\0{section_id}\0{span_identity}"
    return f"rsb_{sha256(identity.encode('utf-8')).hexdigest()[:32]}"


def render_source_text(markdown: str, source_spans: list[SourceSpan]) -> str:
    return "\n\n".join(
        markdown[span.start_offset : span.end_offset] for span in source_spans
    )


def map_rendered_spans_to_source(
    *,
    local_spans: list[SourceSpan],
    source_spans: list[SourceSpan],
) -> list[SourceSpan]:
    mapped: list[SourceSpan] = []
    rendered_cursor = 0

    for source_span in source_spans:
        source_length = source_span.end_offset - source_span.start_offset
        rendered_end = rendered_cursor + source_length
        for local_span in local_spans:
            if (
                local_span.start_offset >= rendered_end
                or local_span.end_offset <= rendered_cursor
            ):
                continue
            mapped_span = SourceSpan(
                source_span.start_offset
                + max(local_span.start_offset, rendered_cursor)
                - rendered_cursor,
                source_span.start_offset
                + min(local_span.end_offset, rendered_end)
                - rendered_cursor,
            )
            if mapped_span not in mapped:
                mapped.append(mapped_span)
        rendered_cursor = rendered_end + 2  # 与 source fragment 的双换行连接保持一致。

    return mapped


def _overlaps(target: SourceSpan, source_spans: list[SourceSpan]) -> bool:
    return any(
        span.start_offset < target.end_offset and span.end_offset > target.start_offset
        for span in source_spans
    )
