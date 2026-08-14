"""将权威 Markdown 解析为跨能力共享的文档结构事实。

``DocumentStructure`` 是 INDEX 流水线最上游的产物之一，所有下游能力（ReadingBlock、
RetrievalChunk、知识图谱）都基于它派生。本模块负责：
- 识别 Markdown 的标题、页码标记、锚点。
- 按结构特征决定 ``StructureMode``（SECTIONED / FLAT_TEXT / EMPTY）。
- SECTIONED 模式下构建带父子关系和子树范围的 Section 树。
"""

from hashlib import sha256
from typing import Literal

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
    """解析标题、页标记和锚点，并保留原始 Python 字符坐标。

    参数:
        resource_id: 资源 ID；用于派生 Section ID 的命名空间。
        content_revision: 内容 revision；与 resource_id 共同构成 Section ID 前缀。
        markdown: 权威 Markdown 原文。

    返回:
        ``DocumentStructure`` 实例，包含 mode、sections、pages、anchors；
        所有 span 都直接指向 ``markdown`` 的 Python 字符偏移，可直接用于切片。
    """
    if not resource_id:
        raise ValueError("resource_id must not be empty")
    if not content_revision:
        raise ValueError("content_revision must not be empty")

    blocks = MarkdownParser().parse(markdown)
    mode = _structure_mode(blocks)

    return DocumentStructure(
        mode=mode,
        total_length=len(markdown),
        # 只有 SECTIONED 模式才构建 Section 树；FLAT_TEXT 由 ``build_flat_text_sections`` 处理。
        sections=(
            _build_sections(
                resource_id=resource_id,
                content_revision=content_revision,
                markdown=markdown,
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
    """根据 block 类型决定文档结构模式。

    优先级：
    1. 只要存在 HEADING 块即视为 SECTIONED（按章节切分）。
    2. 否则若存在任何非页码标记的有效文本块则视为 FLAT_TEXT（无标题平文）。
    3. 否则视为 EMPTY（无可索引内容）。
    """
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
    """从页码标记构建 PageRange 列表。

    每个页码标记定义一个页面的起点；页面范围延伸到下一个页码标记之前（或文档末尾）。
    页码标签必须存在且唯一，否则视为结构错误。
    """
    markers = [block for block in blocks if block.block_kind is BlockKind.PAGE_MARKER]
    pages: list[PageRange] = []
    seen_labels: set[str] = set()

    for index, marker in enumerate(markers):
        if marker.start_offset is None:
            raise ValueError("page marker is missing its source offset")

        page_label = marker.metadata.get("page_label")
        if not isinstance(page_label, str) or not page_label:
            raise ValueError("page marker is missing its page label")
        # 同一文档内页码标签不允许重复，否则无法稳定定位页面。
        if page_label in seen_labels:
            raise ValueError(f"duplicate page label: {page_label}")
        seen_labels.add(page_label)

        # 当前页的结束位置：下一个页码标记的起点，或文档末尾。
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
    """从 block 元数据中收集锚点。

    某些 block（如 HTML 锚点、特殊标记）会在 metadata 中携带 anchor_label；
    本函数把它们提取为 ``DocumentAnchor``，source_span 指向该 block 在原文中的范围。
    """
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
    markdown: str,
    text_length: int,
    blocks: tuple[TextBlock, ...],
) -> list[Section]:
    """标题跳级时以最近的较浅标题为父节点，并在闭合时收敛子树范围。

    算法要点：
    - 创建一个虚拟 root（level 0），own_span 覆盖“第一个标题之前的全部内容”
      （通常是文档元信息、前言等），subtree_span 覆盖整篇文档。
    - 维护一个 ``open_section_indexes`` 栈，记录当前尚未闭合的 Section。
    - 遇到新标题时，先把栈顶所有“level >= 当前标题 level”的 Section 闭合：
      闭合意味着把 subtree_span 的 end 截断到当前标题起点。
    - 新 Section 的父节点是闭合后栈顶的 Section（若无则 root）。
    - 子树范围初始为 [start, text_length]，待后续更深的标题或新同级标题触发闭合时再收敛。
    """
    headings = [block for block in blocks if block.block_kind is BlockKind.HEADING]
    first_heading_start = headings[0].start_offset
    if first_heading_start is None:
        raise ValueError("heading is missing its source offset")

    # 虚拟根 Section：覆盖第一个标题之前的全部内容（前言/文档头）。
    root_content_spans = _content_spans(blocks, 0, first_heading_start)
    root = Section(
        section_id=_build_section_id(
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
        content_spans=root_content_spans,
        preview=_build_section_preview(markdown, root_content_spans),
    )
    sections = [root]
    # 当前尚未闭合的 Section 在 ``sections`` 列表中的下标栈。
    open_section_indexes: list[int] = []
    # 每个 Section 下已有子 Section 数量，用于派生 ordinal。
    child_counts: dict[str, int] = {}

    for heading_index, heading in enumerate(headings):
        if heading.start_offset is None or heading.end_offset is None:
            raise ValueError("heading is missing its source offset")
        heading_level = heading.metadata.get("heading_level")
        title = heading.metadata.get("title")
        if not isinstance(heading_level, int) or heading_level <= 0:
            raise ValueError("heading has an invalid level")
        if not isinstance(title, str) or not title:
            raise ValueError("heading has an invalid title")

        # 闭合所有 level >= 当前 heading_level 的 Section：
        # 把它们的 subtree_span.end_offset 收敛到当前 heading 起点。
        # 这处理了“同级标题”、“跳级返回更浅标题”两种情况。
        while (
            open_section_indexes
            and sections[open_section_indexes[-1]].level >= heading_level
        ):
            closed = sections[open_section_indexes.pop()]
            closed.subtree_span = SourceSpan(
                closed.subtree_span.start_offset,
                heading.start_offset,
            )

        # 父节点为闭合后栈顶 Section；若栈为空（标题 level 跳到很浅）则挂到 root。
        parent = sections[open_section_indexes[-1]] if open_section_indexes else root
        ordinal = child_counts.get(parent.section_id, 0)
        child_counts[parent.section_id] = ordinal + 1
        # 当前 Section 的 own_span 终点：下一个标题的起点，或文档末尾。
        next_heading_start = (
            headings[heading_index + 1].start_offset
            if heading_index + 1 < len(headings)
            else text_length
        )
        if next_heading_start is None:
            raise ValueError("heading is missing its source offset")

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
    """保留 Section 直属语义块，确定性 READ 不依赖 ReadingBlock 分块结果。"""
    return [
        SourceSpan(block.start_offset, block.end_offset)
        for block in blocks
        if block.block_kind not in {BlockKind.HEADING, BlockKind.PAGE_MARKER}
        and block.text.strip()
        and block.start_offset is not None
        and block.end_offset is not None
        and start_offset <= block.start_offset
        and block.end_offset <= end_offset
    ]


def _build_section_preview(markdown: str, source_spans: list[SourceSpan]) -> str:
    """从权威直属正文生成导航预览，不借用 ReadingBlock 分块结果。"""
    return " ".join(
        markdown[span.start_offset : span.end_offset].replace("\n", " ").strip()
        for span in source_spans
    )[:500]


def _build_section_id(
    *,
    resource_id: str,
    content_revision: str,
    kind: Literal["root", "heading", "flat_text"],
    start_offset: int,
    end_offset: int,
) -> str:
    """基于资源、revision、kind、span 边界生成稳定 Section ID。

    kind 取值 "root" / "heading" / "flat_text"，区分不同来源的 Section；
    span 边界参与哈希，使同一段内容在不同解析规则下生成的 ID 不会冲突。
    """
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
