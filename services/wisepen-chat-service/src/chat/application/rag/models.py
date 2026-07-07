from __future__ import annotations

from dataclasses import dataclass

from chat.application.rag.answerability import RagAnswerabilityWarning, RagHardGateDecision
from chat.application.rag.context_builder import RagContextPackage, RagDirectEvidence
from chat.application.rag.retrieval import (
    RagExactFilter,
    RagPermissionScope,
    RagRetrievalProfile,
    ScoredChunk,
)
from chat.application.utils.ranking_engine.models import RankedCandidate


@dataclass(frozen=True, slots=True)
class RagKnowledgeSearchRequest:
    query: str
    resource_id: str
    corpus_version: str
    retrieval_profile: RagRetrievalProfile = RagRetrievalProfile.BALANCED
    exact_filter: RagExactFilter | None = None
    permission_scope: RagPermissionScope | None = None
    top_k: int = 20
    candidate_limit: int = 100
    elastic_prefilter_limit: int = 1000


@dataclass(frozen=True, slots=True)
class RagKnowledgeSearchResult:
    resource_id: str
    corpus_version: str
    retrieval_profile: RagRetrievalProfile
    elastic_candidate_chunk_ids: tuple[str, ...] | None
    retrieved_chunks: tuple[ScoredChunk, ...]
    ranked: tuple[RankedCandidate, ...]
    hard_gate: RagHardGateDecision
    direct_evidence: tuple[RagDirectEvidence, ...] = ()
    answerability_warning: RagAnswerabilityWarning | None = None
    context: RagContextPackage | None = None

    @property
    def should_continue(self) -> bool:
        return self.hard_gate.should_continue
