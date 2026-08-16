"""将权威 Markdown 解析为跨能力共享的文档结构事实。"""

from hashlib import sha256
from typing import Literal

from rag.domain.models.structure import (
    DocumentAnchor,
    DocumentStructure,
    PageRange,
    Section,
    StructureMode,
)
from rag.utils.chunkers import (
    BlockKind,
    ChunkDocument,
    MarkdownChunker,
    SourceSpan,
    TextBlock,
)
from rag.utils.chunkers.markdown import MarkdownParser

# FLAT_TEXT 模式下单个合成 Section 的最大可见字符数。
_FLAT_TEXT_SECTION_MAX_CHARACTERS = 4000


def parse_document_structure(
    *,
    resource_id: str,
    content_revision: str,
    markdown: str,
) -> DocumentStructure:
    """解析标题、页标记和锚点，并保留原始 Python 字符坐标。

    sections 按模式构建：SECTIONED 构建标题树，FLAT_TEXT 生成按
    _FLAT_TEXT_SECTION_MAX_CHARACTERS 切分的合成 Section，EMPTY 为空列表。
    调用方直接消费 structure.sections，无需感知模式差异。
    """
    blocks = MarkdownParser().parse(markdown)
    mode = _structure_mode(blocks)

    if mode is StructureMode.SECTIONED:
        sections = _build_sections(
            resource_id=resource_id,
            content_revision=content_revision,
            markdown=markdown,
            blocks=blocks,
        )
    elif mode is StructureMode.FLAT_TEXT:
        sections = _build_flat_text_sections(
            resource_id=resource_id,
            content_revision=content_revision,
            markdown=markdown,
        )
    else:
        sections = []

    return DocumentStructure(
        mode=mode,
        total_length=len(markdown),
        sections=sections,
        pages=_build_pages(markdown=markdown, blocks=blocks),
        anchors=_build_anchors(blocks),
    )


def _structure_mode(blocks: tuple[TextBlock, ...]) -> StructureMode:
    # 存在任何 HEADING 块即视为 SECTIONED。
    if any(block.block_kind is BlockKind.HEADING for block in blocks):
        return StructureMode.SECTIONED

    # 存在任何非页码标记的有效文本块即视为 FLAT_TEXT。
    if any(
        block.block_kind is not BlockKind.PAGE_MARKER and block.text.strip()
        for block in blocks
    ):
        return StructureMode.FLAT_TEXT
    return StructureMode.EMPTY


def _build_pages(
    *,
    markdown: str,
    blocks: tuple[TextBlock, ...],
) -> list[PageRange]:
    """从页码标记构建 PageRange 列表。"""
    text_length = len(markdown)
    markers = [block for block in blocks if block.block_kind is BlockKind.PAGE_MARKER]
    pages: list[PageRange] = []
    seen_labels: set[str] = set()

    for idx, marker in enumerate(markers):
        page_label = marker.metadata.get("page_label")
        # 同一文档内页码标签不允许重复。
        if page_label in seen_labels:
            raise ValueError(f"duplicate page label: {page_label}")
        seen_labels.add(page_label)

        # 当前页的结束位置为下一个页码标记的起点，或文档末尾。
        end_offset = (
            markers[idx + 1].start_offset if idx + 1 < len(markers) else text_length
        )

        pages.append(
            PageRange(
                page_index=idx,
                page_label=page_label,
                source_span=SourceSpan(marker.start_offset, end_offset),
            )
        )
    return pages


def _build_anchors(blocks: tuple[TextBlock, ...]) -> list[DocumentAnchor]:
    """从 block 元数据中收集表格、图片等锚点。"""
    anchors: list[DocumentAnchor] = []
    for block in blocks:
        anchor_label = block.metadata.get("anchor_label")
        if anchor_label is None:
            continue

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
    markdown: str,
    blocks: tuple[TextBlock, ...],
) -> list[Section]:
    text_length = len(markdown)
    headings = [block for block in blocks if block.block_kind is BlockKind.HEADING]
    first_heading_start = headings[0].start_offset

    # 创建虚拟根 section，覆盖第一个标题之前的全部内容（前言/文档头）。
    root_content_spans = _content_spans(blocks, 0, first_heading_start)

    # 前言非空时赋予合成标题，使 READ 大纲暴露可导航的前言入口
    # 前言为空时保持无名 root，大纲直接从一级标题展开。
    root_title = "文档开头" if root_content_spans else ""
    root = Section(
        section_id=_build_section_id(
            resource_id=resource_id,
            content_revision=content_revision,
            kind="root",
            start_offset=0,
            end_offset=first_heading_start,
        ),
        title=root_title,
        level=0,
        parent_section_id=None,
        ordinal=0,
        section_path=[root_title] if root_title else [],
        own_span=SourceSpan(0, first_heading_start),
        subtree_span=SourceSpan(0, text_length),
        content_spans=root_content_spans,
        preview=_build_section_preview(markdown, root_content_spans),
    )

    sections = [root]
    open_section_indexes: list[int] = []    # 当前尚未闭合的 Section 在 sections 列表中的下标栈。
    child_counts: dict[str, int] = {}   # 每个 Section 下已有子 Section 数量，用于派生 ordinal。

    for heading_index, heading in enumerate(headings):
        heading_level = heading.metadata.get("heading_level")
        title = heading.metadata.get("title")

        # 维护一个单调递增栈，确保栈中标题层级严格小于当前标题
        while (
            # 仍存在未闭合 section
            open_section_indexes
            # 且栈顶标题 level >= 当前标题
            and sections[open_section_indexes[-1]].level >= heading_level
        ):
            # 说明栈顶标题已经闭合，弹出栈顶标题
            closed = sections[open_section_indexes.pop()]
            closed.subtree_span = SourceSpan(
                closed.subtree_span.start_offset,
                heading.start_offset,
            )

        # 如果栈非空，则父节点为栈顶标题；否则为 root
        parent = sections[open_section_indexes[-1]] if open_section_indexes else root
        ordinal = child_counts.get(parent.section_id, 0)
        child_counts[parent.section_id] = ordinal + 1
        # 当前 section 的 own_span 终点为下一个标题的起点，或文档末尾。
        next_heading_start = (
            headings[heading_index + 1].start_offset
            if heading_index + 1 < len(headings)
            else text_length
        )

        content_spans = _content_spans(
            blocks,
            heading.end_offset,
            next_heading_start,
        )
        section = Section(
            section_id=_build_section_id(
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
            # section_path 由 markdown parser 在解析阶段维护，直接复用以保持一致。
            section_path=list(heading.section_path),
            own_span=SourceSpan(heading.start_offset, next_heading_start),
            # subtree_span 初始覆盖到文档末尾；待后续闭合时再收敛。
            subtree_span=SourceSpan(heading.start_offset, text_length),
            content_spans=content_spans,
            preview=_build_section_preview(markdown, content_spans),
        )
        sections.append(section)
        open_section_indexes.append(len(sections) - 1)

    return sections


def _content_spans(
    blocks: tuple[TextBlock, ...],
    start_offset: int,
    end_offset: int,
) -> list[SourceSpan]:
    """Section 直属语义块。"""
    return [
        SourceSpan(block.start_offset, block.end_offset)
        for block in blocks
        if block.block_kind not in {BlockKind.HEADING, BlockKind.PAGE_MARKER}
        and block.text.strip()
        and start_offset <= block.start_offset
        and block.end_offset <= end_offset
    ]


def _build_section_preview(markdown: str, source_spans: list[SourceSpan]) -> str:
    """从权威直属正文生成导航预览。"""
    return " ".join(
        markdown[span.start_offset : span.end_offset].strip()
        for span in source_spans
    )[:500]


def _build_flat_text_sections(
    *,
    resource_id: str,
    content_revision: str,
    markdown: str,
) -> list[Section]:
    """把无标题正文按 _FLAT_TEXT_SECTION_MAX_CHARACTERS 拆成无重叠导航 Section。

    无标题文档在 MarkdownChunker 中退化为“TextBlock 按字符预算装箱 +
    超长 block 递归切分”，直接使用其输出。
    """
    result = MarkdownChunker(
        max_characters=_FLAT_TEXT_SECTION_MAX_CHARACTERS,
    ).chunk(document=ChunkDocument(text=markdown))
    sections: list[Section] = []
    
    for index, source_spans in enumerate(result.chunks):
        spans = list(source_spans.source_spans)
        own_span = SourceSpan(spans[0].start_offset, spans[-1].end_offset)
        title = f"全文片段 {index + 1}"
        sections.append(
            Section(
                section_id=_build_section_id(
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
                content_spans=spans,
                preview=_build_section_preview(markdown, spans),
            )
        )
    return sections


def _build_section_id(
    *,
    resource_id: str,
    content_revision: str,
    kind: Literal["root", "heading", "flat_text"],
    start_offset: int,
    end_offset: int,
) -> str:
    """基于资源、revision、kind、span 边界生成稳定 Section ID。"""
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
