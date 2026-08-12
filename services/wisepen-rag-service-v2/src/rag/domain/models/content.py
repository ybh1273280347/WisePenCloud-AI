"""资源内容、发布 revision、正文块和读取视图的稳定领域模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from rag.domain.models.structure import PageRange, Section, StructureMode
from rag.utils.chunkers import SourceSpan

if TYPE_CHECKING:
    from rag.domain.models.evidence import EvidenceRecord


@dataclass(slots=True)
class ResourceIndexState:
    """一个资源当前 staged/applied revision 指针。"""

    resource_id: str
    staged_content_revision: str | None = None
    staged_document_version: int | None = None
    applied_content_revision: str | None = None
    applied_document_version: int | None = None


@dataclass(slots=True)
class ContentRevision:
    """一次可独立发布的权威 Markdown 版本。"""

    resource_id: str
    content_revision: str
    document_version: int
    content_hash: str
    index_schema_version: str
    structure_mode: StructureMode
    total_length: int
    pages: list[PageRange] = field(default_factory=list)


@dataclass(slots=True)
class SourcePart:
    """超大 Markdown 的连续存储分片。"""

    resource_id: str
    content_revision: str
    part_index: int
    source_span: SourceSpan
    text: str


@dataclass(slots=True)
class ReadingBlock:
    """一个 Section 内可独立读取且能精确回源的有序正文块。"""

    block_id: str
    section_id: str
    ordinal: int
    raw_text: str
    source_spans: list[SourceSpan] = field(default_factory=list)
    page_labels: list[str] = field(default_factory=list)
    anchor_labels: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DocumentStructureResult:
    """READ structure 的读取结果，不包含正文窗口。"""

    revision: ContentRevision
    sections: list[Section] = field(default_factory=list)


@dataclass(slots=True)
class ContentWindow:
    """READ 返回的正文窗口，source_span 使用 Python 字符偏移。"""

    text: str
    source_span: SourceSpan
    source_spans: list[SourceSpan] = field(default_factory=list)
    page_labels: list[str] = field(default_factory=list)
    section_ids: list[str] = field(default_factory=list)
    anchor_labels: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SectionFrontier:
    """围绕一个 Section 的标题树探索边界。"""

    parent: Section | None = None
    previous: Section | None = None
    next: Section | None = None
    children: list[Section] = field(default_factory=list)


@dataclass(slots=True)
class SectionContent:
    """Section 正文及相邻标题入口。"""

    section: Section
    reading_blocks: list[ReadingBlock] = field(default_factory=list)
    frontier: SectionFrontier = field(default_factory=SectionFrontier)


@dataclass(slots=True)
class SectionView:
    """Agent 可读取并继续展开的标题树节点视图。"""

    resource_id: str
    content_revision: str
    section: Section
    reading_blocks: list[ReadingBlock] = field(default_factory=list)
    frontier: SectionFrontier = field(default_factory=SectionFrontier)
    evidence: list[EvidenceRecord] = field(default_factory=list)
