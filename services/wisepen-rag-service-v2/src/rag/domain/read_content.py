"""read 能力跨 application/persistence 共享的内容结果事实。"""

from dataclasses import dataclass, field

from rag.domain.content_revision import ContentRevision
from rag.domain.document_structure import Section
from rag.domain.reading import ReadingBlock
from rag.utils.chunkers import SourceSpan


@dataclass(slots=True)
class DocumentStructureResult:
    revision: ContentRevision
    sections: list[Section] = field(default_factory=list)


@dataclass(slots=True)
class ContentWindow:
    text: str
    source_span: SourceSpan
    source_spans: list[SourceSpan] = field(default_factory=list)
    page_labels: list[str] = field(default_factory=list)
    section_ids: list[str] = field(default_factory=list)
    anchor_labels: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SectionFrontier:
    parent: Section | None = None
    previous: Section | None = None
    next: Section | None = None
    children: list[Section] = field(default_factory=list)


@dataclass(slots=True)
class SectionContent:
    section: Section
    reading_blocks: list[ReadingBlock] = field(default_factory=list)
    frontier: SectionFrontier = field(default_factory=SectionFrontier)
