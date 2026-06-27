from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ContextIndexingInput:
    """单个 child chunk 的 Context Indexing 输入。"""

    parent_text: str
    child_text: str
    document_title: str = ""
    section_path: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ContextIndexingResult:
    """Context Indexing 输出，用于后续 embedding / lexical / graph extraction。"""

    evidence_text: str
    indexing_text: str
    context_summary: str = ""
    important_terms: tuple[str, ...] = ()
    usage_tokens: int = 0
    metadata: dict[str, object] = field(default_factory=dict)
