from __future__ import annotations

from dataclasses import dataclass

from chat.application.rag.answerability import RagAnswerabilityWarning
from chat.application.rag.retrieval import RagRetrievalChannel


@dataclass(frozen=True, slots=True)
class RagMatchedChildChunk:
    """命中父块的子块定位信息。"""

    chunk_id: str
    text: str
    page_label: str | None = None
    section_path: tuple[str, ...] = ()
    anchor_labels: tuple[str, ...] = ()
    retrieval_channels: tuple[RagRetrievalChannel, ...] = ()


@dataclass(frozen=True, slots=True)
class RagDirectEvidence:
    """通过 ranking 和 hard gate 后可交给主模型的直接证据。"""

    citation_id: str
    parent_chunk_id: str
    resource_id: str
    document_version: str
    corpus_version: str
    text: str
    citation_anchor: str
    rank: int
    score: float
    page_label: str | None = None
    section_path: tuple[str, ...] = ()
    anchor_labels: tuple[str, ...] = ()
    matched_child_chunks: tuple[RagMatchedChildChunk, ...] = ()
    elastic_prefiltered: bool = False


@dataclass(frozen=True, slots=True)
class RagContextBuildRequest:
    query: str
    direct_evidence: tuple[RagDirectEvidence, ...]
    answerability_warning: RagAnswerabilityWarning | None = None


@dataclass(frozen=True, slots=True)
class RagContextPackage:
    query: str
    direct_evidence: tuple[RagDirectEvidence, ...]
    context_text: str
    answerability_warning: RagAnswerabilityWarning | None = None
