"""跨索引、读取和核验能力共享的正文阅读事实。"""

from dataclasses import dataclass, field

from rag.utils.chunkers import SourceSpan


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
