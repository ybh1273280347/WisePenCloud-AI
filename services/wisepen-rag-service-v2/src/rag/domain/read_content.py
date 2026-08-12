"""跨仓储、应用和 API 使用的已发布正文读取契约。"""

from dataclasses import dataclass, field

from rag.domain.content_revision import ContentRevision
from rag.domain.document_structure import Section
from rag.domain.evidence import EvidenceRecord
from rag.domain.reading import ReadingBlock
from rag.utils.chunkers import SourceSpan


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
