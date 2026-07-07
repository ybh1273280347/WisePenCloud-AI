from __future__ import annotations

from chat.application.rag.answerability import (
    AnswerabilityHardGate,
    AnswerabilitySoftGate,
    RagAnswerabilityInput,
)
from chat.application.rag.utils import permission_scope_key
from chat.application.rag.cache import RagEvidenceMaterializationCacheScope
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
from chat.application.rag.graph import (
    RagGraphEnhancementRequest,
    RagGraphEnhancementResult,
)
from chat.application.rag.ranking import RagEvidenceRankingRequest, RagEvidenceRankingService
from chat.application.rag.retrieval import RagRetrievalPipeline, RagRetrievalPipelineRequest


class RagKnowledgeSearcher:
    """执行定稿中的 RAG 主检索链路。"""

    __slots__ = (
        "_hard_gate",
        "_context_builder",
        "_evidence_materializer",
        "_ranking_service",
        "_retrieval_pipeline",
        "_soft_gate",
    )

    def __init__(
            self,
            *,
            retrieval_pipeline: RagRetrievalPipeline,
            ranking_service: RagEvidenceRankingService,
            hard_gate: AnswerabilityHardGate,
            soft_gate: AnswerabilitySoftGate,
            evidence_materializer: RagEvidenceMaterializer,
            context_builder: RagContextBuilder,
    ) -> None:
        self._retrieval_pipeline = retrieval_pipeline
        self._ranking_service = ranking_service
        self._hard_gate = hard_gate
        self._soft_gate = soft_gate
        self._evidence_materializer = evidence_materializer
        self._context_builder = context_builder

    async def search(self, request: RagKnowledgeSearchRequest) -> RagKnowledgeSearchResult:
        retrieval = await self._retrieval_pipeline.retrieve(
            RagRetrievalPipelineRequest(
                query=request.query,
                resource_id=request.resource_id,
                retrieval_profile=request.retrieval_profile,
                keywords=request.keywords,
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
                hard_gate=hard_gate,
            )

        direct_evidence = await self._evidence_materializer.materialize(
            RagEvidenceMaterializeRequest(
                ranked=ranking.ranked,
                retrieved_chunks=retrieval.chunks,
                cache_scope=_build_materialization_cache_scope(request),
            )
        )
        warning = await self._soft_gate.evaluate(answerability_input)
        graph_enhancement = await self._enhance_with_graph(
            request=request,
            direct_evidence=direct_evidence,
            warning=warning,
        )
        context = self._context_builder.build(
            RagContextBuildRequest(
                query=request.query,
                direct_evidence=direct_evidence,
                answerability_warning=warning,
                graph_evidence=graph_enhancement.graph_evidence,
                ontology_hints=graph_enhancement.ontology_hints,
            )
        )
        return RagKnowledgeSearchResult(
            hard_gate=hard_gate,
            direct_evidence=direct_evidence,
            answerability_warning=warning,
            graph_enhancement=graph_enhancement,
            context=context,
        )

    async def _enhance_with_graph(
            self,
            *,
            request: RagKnowledgeSearchRequest,
            direct_evidence: tuple,
            warning,
    ) -> RagGraphEnhancementResult:
        return await self._retrieval_pipeline.enhance_graph(
            RagGraphEnhancementRequest(
                query=request.query,
                resource_id=request.resource_id,
                direct_evidence=direct_evidence,
                answerability_warning=warning,
                permission_scope=request.permission_scope,
            )
        )


def _build_materialization_cache_scope(
        request: RagKnowledgeSearchRequest,
) -> RagEvidenceMaterializationCacheScope | None:
    if request.permission_scope is None:
        return None

    user_id = request.permission_scope.user_id.strip()
    session_id = request.session_id.strip()
    if not user_id or not session_id:
        return None

    return RagEvidenceMaterializationCacheScope(
        user_id=user_id,
        session_id=session_id,
        resource_id=request.resource_id,
        permission_scope_key=permission_scope_key(request.permission_scope.group_role_map),
    )
