from __future__ import annotations

from chat.application.rag.answerability import (
    AnswerabilityHardGate,
    AnswerabilitySoftGate,
    RagAnswerabilityInput,
)
from chat.application.rag.context_builder import (
    RagContextBuildRequest,
    RagContextBuilder,
    RagEvidenceMaterializeRequest,
    RagEvidenceMaterializer,
)
from chat.application.rag.models import (
    RagKnowledgeSearchRequest,
    RagKnowledgeSearchResult,
)
from chat.application.rag.ranking import RagEvidenceRankingRequest, RagEvidenceRankingService
from chat.application.rag.retrieval import RagHybridRetrievalRequest, RagHybridRetriever


class RagKnowledgeSearcher:
    """执行定稿中的 RAG 主检索链路。"""

    __slots__ = (
        "_hard_gate",
        "_context_builder",
        "_evidence_materializer",
        "_ranking_service",
        "_retriever",
        "_soft_gate",
    )

    def __init__(
            self,
            *,
            retriever: RagHybridRetriever,
            ranking_service: RagEvidenceRankingService,
            hard_gate: AnswerabilityHardGate,
            soft_gate: AnswerabilitySoftGate,
            evidence_materializer: RagEvidenceMaterializer,
            context_builder: RagContextBuilder,
    ) -> None:
        self._retriever = retriever
        self._ranking_service = ranking_service
        self._hard_gate = hard_gate
        self._soft_gate = soft_gate
        self._evidence_materializer = evidence_materializer
        self._context_builder = context_builder

    async def search(self, request: RagKnowledgeSearchRequest) -> RagKnowledgeSearchResult:
        retrieval = await self._retriever.retrieve(
            RagHybridRetrievalRequest(
                query=request.query,
                resource_id=request.resource_id,
                corpus_version=request.corpus_version,
                retrieval_profile=request.retrieval_profile,
                exact_filter=request.exact_filter,
                permission_scope=request.permission_scope,
                candidate_limit=request.candidate_limit,
                elastic_prefilter_limit=request.elastic_prefilter_limit,
            )
        )
        ranking = await self._ranking_service.rank(
            RagEvidenceRankingRequest(
                query=request.query,
                chunks=retrieval.chunks,
                top_k=request.top_k,
                candidate_limit=request.candidate_limit,
            )
        )

        answerability_input = RagAnswerabilityInput(
            query=request.query,
            retrieval_profile=request.retrieval_profile.value,
            ranked=ranking.ranked,
        )
        hard_gate = self._hard_gate.decide(answerability_input)
        if not hard_gate.should_continue:
            return RagKnowledgeSearchResult(
                resource_id=request.resource_id,
                corpus_version=request.corpus_version,
                retrieval_profile=request.retrieval_profile,
                elastic_candidate_chunk_ids=retrieval.elastic_candidate_chunk_ids,
                retrieved_chunks=retrieval.chunks,
                ranked=ranking.ranked,
                hard_gate=hard_gate,
            )

        direct_evidence = await self._evidence_materializer.materialize(
            RagEvidenceMaterializeRequest(
                ranked=ranking.ranked,
                retrieved_chunks=retrieval.chunks,
                elastic_candidate_chunk_ids=retrieval.elastic_candidate_chunk_ids,
            )
        )
        warning = await self._soft_gate.evaluate(answerability_input)
        context = self._context_builder.build(
            RagContextBuildRequest(
                query=request.query,
                direct_evidence=direct_evidence,
                answerability_warning=warning,
            )
        )
        return RagKnowledgeSearchResult(
            resource_id=request.resource_id,
            corpus_version=request.corpus_version,
            retrieval_profile=request.retrieval_profile,
            elastic_candidate_chunk_ids=retrieval.elastic_candidate_chunk_ids,
            retrieved_chunks=retrieval.chunks,
            ranked=ranking.ranked,
            hard_gate=hard_gate,
            direct_evidence=direct_evidence,
            answerability_warning=warning,
            context=context,
        )
