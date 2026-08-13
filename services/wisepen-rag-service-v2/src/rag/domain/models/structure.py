"""跨 RAG 能力共享的文档结构事实。"""

from dataclasses import dataclass, field
from enum import StrEnum

from rag.utils.chunkers import SourceSpan


class StructureMode(StrEnum):
    """权威正文可提供的结构层级。"""

    SECTIONED = "sectioned"
    FLAT_TEXT = "flat_text"
    EMPTY = "empty"


@dataclass(slots=True)
class PageRange:
    """一个页标签在原始 Markdown 中覆盖的范围。"""

    page_index: int
    page_label: str
    source_span: SourceSpan


@dataclass(slots=True)
class DocumentAnchor:
    """表格、图片或公式锚点及其精确原文范围。"""

    label: str
    source_span: SourceSpan


@dataclass(slots=True)
class Section:
    """标题树中的 Section 及其直属正文和子树范围。"""

    section_id: str
    title: str
    level: int
    parent_section_id: str | None
    ordinal: int
    section_path: list[str]
    own_span: SourceSpan
    subtree_span: SourceSpan
    preview: str = ""


@dataclass(slots=True)
class SectionTreeNode:
    """READ structure 返回给 Agent 的标题树节点。"""

    section_id: str
    title: str
    level: int
    section_path: list[str]
    has_content: bool
    start_page_label: str | None = None
    end_page_label: str | None = None
    # 覆盖当前标题子树的页码标签，用来把“看目录”直接衔接到按页读取。
    page_labels: list[str] = field(default_factory=list)
    children: list["SectionTreeNode"] = field(default_factory=list)


@dataclass(slots=True)
class DocumentStructure:
    """一次 Markdown 结构解析产生的稳定事实。"""

    mode: StructureMode
    total_length: int
    sections: list[Section] = field(default_factory=list)
    pages: list[PageRange] = field(default_factory=list)
    anchors: list[DocumentAnchor] = field(default_factory=list)
