"""将权威 Markdown 解析为跨能力共享的文档结构事实。"""

from hashlib import sha256

from rag.domain.models.structure import (
    DocumentAnchor,
    DocumentStructure,
    PageRange,
    Section,
    StructureMode,
)
from rag.utils.chunkers import BlockKind, SourceSpan, TextBlock
from rag.utils.chunkers.markdown import MarkdownParser


def parse_document_structure(
    *,
    resource_id: str,
    content_revision: str,
    markdown: str,
) -> DocumentStructure:
    """解析标题、页标记和锚点，并保留原始 Python 字符坐标。"""
    if not resource_id:
        raise ValueError("resource_id must not be empty")
    if not content_revision:
        raise ValueError("content_revision must not be empty")

    blocks = MarkdownParser().parse(markdown)
    mode = _structure_mode(blocks)

    return DocumentStructure(
        mode=mode,
        total_length=len(markdown),
        sections=(
            _build_sections(
                resource_id=resource_id,
                content_revision=content_revision,
                text_length=len(markdown),
                blocks=blocks,
            )
            if mode is StructureMode.SECTIONED
            else []
        ),
        pages=_build_pages(text_length=len(markdown), blocks=blocks),
        anchors=_build_anchors(blocks),
    )


def _structure_mode(blocks: tuple[TextBlock, ...]) -> StructureMode:
    if any(block.block_kind is BlockKind.HEADING for block in blocks):
        return StructureMode.SECTIONED
    if any(
        block.block_kind is not BlockKind.PAGE_MARKER and block.text.strip()
        for block in blocks
    ):
        return StructureMode.FLAT_TEXT
    return StructureMode.EMPTY


def _build_pages(
    *,
    text_length: int,
    blocks: tuple[TextBlock, ...],
) -> list[PageRange]:
    markers = [block for block in blocks if block.block_kind is BlockKind.PAGE_MARKER]
    pages: list[PageRange] = []
    seen_labels: set[str] = set()

    for index, marker in enumerate(markers):
        if marker.start_offset is None:
            raise ValueError("page marker is missing its source offset")

        page_label = marker.metadata.get("page_label")
        if not isinstance(page_label, str) or not page_label:
            raise ValueError("page marker is missing its page label")
        if page_label in seen_labels:
            raise ValueError(f"duplicate page label: {page_label}")
        seen_labels.add(page_label)

        end_offset = (
            markers[index + 1].start_offset if index + 1 < len(markers) else text_length
        )
        if end_offset is None:
            raise ValueError("page marker is missing its source offset")
        pages.append(
            PageRange(
                page_index=index,
                page_label=page_label,
                source_span=SourceSpan(marker.start_offset, end_offset),
            )
        )

    return pages


def _build_anchors(blocks: tuple[TextBlock, ...]) -> list[DocumentAnchor]:
    anchors: list[DocumentAnchor] = []
    for block in blocks:
        anchor_label = block.metadata.get("anchor_label")
        if anchor_label is None:
            continue
        if not isinstance(anchor_label, str) or not anchor_label:
            raise ValueError("document anchor has an invalid label")
        if block.start_offset is None or block.end_offset is None:
            raise ValueError(
                f"document anchor {anchor_label} is missing its source span"
            )
        anchors.append(
            DocumentAnchor(
                label=anchor_label,
                source_span=SourceSpan(block.start_offset, block.end_offset),
            )
        )
    return anchors


def _build_sections(
    *,
    resource_id: str,
    content_revision: str,
    text_length: int,
    blocks: tuple[TextBlock, ...],
) -> list[Section]:
    """标题跳级时以最近的较浅标题为父节点，并在闭合时收敛子树范围。"""
    headings = [block for block in blocks if block.block_kind is BlockKind.HEADING]
    first_heading_start = headings[0].start_offset
    if first_heading_start is None:
        raise ValueError("heading is missing its source offset")

    root = Section(
        section_id=build_section_id(
            resource_id=resource_id,
            content_revision=content_revision,
            kind="root",
            start_offset=0,
            end_offset=first_heading_start,
        ),
        title="",
        level=0,
        parent_section_id=None,
        ordinal=0,
        section_path=[],
        own_span=SourceSpan(0, first_heading_start),
        subtree_span=SourceSpan(0, text_length),
    )
    sections = [root]
    open_section_indexes: list[int] = []
    child_counts: dict[str, int] = {}

    for heading_index, heading in enumerate(headings):
        if heading.start_offset is None:
            raise ValueError("heading is missing its source offset")
        heading_level = heading.metadata.get("heading_level")
        title = heading.metadata.get("title")
        if not isinstance(heading_level, int) or heading_level <= 0:
            raise ValueError("heading has an invalid level")
        if not isinstance(title, str) or not title:
            raise ValueError("heading has an invalid title")

        while (
            open_section_indexes
            and sections[open_section_indexes[-1]].level >= heading_level
        ):
            closed = sections[open_section_indexes.pop()]
            closed.subtree_span = SourceSpan(
                closed.subtree_span.start_offset,
                heading.start_offset,
            )

        parent = sections[open_section_indexes[-1]] if open_section_indexes else root
        ordinal = child_counts.get(parent.section_id, 0)
        child_counts[parent.section_id] = ordinal + 1
        next_heading_start = (
            headings[heading_index + 1].start_offset
            if heading_index + 1 < len(headings)
            else text_length
        )
        if next_heading_start is None:
            raise ValueError("heading is missing its source offset")

        section = Section(
            section_id=build_section_id(
                resource_id=resource_id,
                content_revision=content_revision,
                kind="heading",
                start_offset=heading.start_offset,
                end_offset=next_heading_start,
            ),
            title=title,
            level=heading_level,
            parent_section_id=parent.section_id,
            ordinal=ordinal,
            section_path=list(heading.section_path),
            own_span=SourceSpan(heading.start_offset, next_heading_start),
            subtree_span=SourceSpan(heading.start_offset, text_length),
        )
        sections.append(section)
        open_section_indexes.append(len(sections) - 1)

    return sections


def build_section_id(
    *,
    resource_id: str,
    content_revision: str,
    kind: str,
    start_offset: int,
    end_offset: int,
) -> str:
    identity = "\0".join(
        (
            resource_id,
            content_revision,
            kind,
            str(start_offset),
            str(end_offset),
        )
    )
    return f"rsec_{sha256(identity.encode('utf-8')).hexdigest()[:32]}"
