from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chat.application.rag.answerability import RagAnswerabilityWarning
    from chat.application.rag.context_builder.models import RagDirectEvidence
    from chat.application.rag.retrieval import RagPermissionScope


@dataclass(frozen=True, slots=True)
class RagGraphEvidence:
    """Neo4j 后置增强找到的补充证据。"""

    chunk_id: str
    document_version: str
    evidence_text: str
    citation_anchor: str
    path: tuple[str, ...] = ()
    related_concepts: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RagOntologyHint:
    """非证据型结构提示，供主模型降低歧义或控制回答边界。"""

    concept: str
    class_candidates: tuple[str, ...] = ()
    relation_type_candidates: tuple[str, ...] = ()
    path_preview: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RagConceptPath:
    source_concept: str
    target_concept: str
    path: tuple[str, ...] = ()
    support_chunk_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RagGraphEnhancementRequest:
    query: str
    resource_id: str
    direct_evidence: tuple[RagDirectEvidence, ...]
    answerability_warning: RagAnswerabilityWarning
    permission_scope: RagPermissionScope | None = None
    limit: int = 5


@dataclass(frozen=True, slots=True)
class RagGraphEnhancementResult:
    graph_evidence: tuple[RagGraphEvidence, ...] = ()
    ontology_hints: tuple[RagOntologyHint, ...] = ()
    concept_paths: tuple[RagConceptPath, ...] = ()

    @property
    def has_content(self) -> bool:
        return bool(self.graph_evidence or self.ontology_hints or self.concept_paths)
