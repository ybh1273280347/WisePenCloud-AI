from __future__ import annotations

from dataclasses import dataclass

from chat.application.rag.answerability import RagAnswerabilityWarning
from chat.application.rag.graph import RagGraphEvidence, RagOntologyHint


@dataclass(frozen=True, slots=True)
class RagDirectEvidence:
    """通过 ranking 和 hard gate 后可交给主模型的直接证据。"""

    citation_id: str
    document_version: str
    text: str
    page_label: str | None = None
    section_path: tuple[str, ...] = ()
    anchor_labels: tuple[str, ...] = ()
    matched_child_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RagContextBuildRequest:
    query: str
    direct_evidence: tuple[RagDirectEvidence, ...]
    answerability_warning: RagAnswerabilityWarning | None = None
    graph_evidence: tuple[RagGraphEvidence, ...] = ()
    ontology_hints: tuple[RagOntologyHint, ...] = ()


@dataclass(frozen=True, slots=True)
class RagContextPackage:
    query: str
    direct_evidence: tuple[RagDirectEvidence, ...]
    context_text: str
    answerability_warning: RagAnswerabilityWarning | None = None
    graph_evidence: tuple[RagGraphEvidence, ...] = ()
    ontology_hints: tuple[RagOntologyHint, ...] = ()
