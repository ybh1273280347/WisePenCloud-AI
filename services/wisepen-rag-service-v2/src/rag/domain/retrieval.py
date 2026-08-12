"""检索块及其权威证据引用。"""

from dataclasses import dataclass, field

from rag.utils.chunkers import SourceSpan


@dataclass(slots=True)
class RetrievalChunk:
    """评分使用的最小正文单位及其 ReadingBlock 归属。"""

    chunk_id: str
    reading_block_id: str
    section_id: str
    section_path: list[str]
    raw_text: str
    index_text: str
    source_spans: list[SourceSpan] = field(default_factory=list)
    page_labels: list[str] = field(default_factory=list)
    anchor_labels: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SourceRef:
    """RetrievalChunk 到 applied revision 权威原文的稳定引用。"""

    ref_id: str
    resource_id: str
    content_revision: str
    chunk_id: str
    reading_block_id: str
    section_id: str
    section_path: list[str]
    source_spans: list[SourceSpan] = field(default_factory=list)
    page_labels: list[str] = field(default_factory=list)
    anchor_labels: list[str] = field(default_factory=list)
