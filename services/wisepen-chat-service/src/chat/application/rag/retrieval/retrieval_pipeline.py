from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from chat.application.rag.answerability import (
    AnswerabilityHardGate,
    AnswerabilitySoftGate,
    RagAnswerabilityInput,
    RagAnswerabilityWarning,
    RagHardGateDecision,
)
from chat.application.rag.cache import RagEvidenceMaterializationCacheScope
from chat.application.rag.context_builder.models import RagDirectEvidence
from chat.application.rag.graph import RagGraphEnhancementRequest, RagGraphEnhancementResult
from chat.application.rag.retrieval.models import (
    RagElasticKeywordFilterRequest,
    RagPermissionScope,
    RagQdrantRetrievalRequest,
    RagRankedChunk,
    RagRetrievalProfile,
    ScoredChunk,
)
from chat.application.rag.retrieval.pipeline import (
    RagElasticFilter,
    RagEvidenceRankingRequest,
    RagEvidenceRankingService,
    RagGraphEnhancement,
    RagQdrantRetriever,
)
from chat.application.utils.ranking_engine.models import RankedCandidate

if TYPE_CHECKING:
    from chat.application.rag.context_builder import RagEvidenceMaterializer


@dataclass(frozen=True, slots=True)
class RagRetrievalPipelineRequest:
    query: str
    resource_id: str
    session_id: str = ""
    retrieval_profile: RagRetrievalProfile = RagRetrievalProfile.BALANCED
    keywords: tuple[str, ...] = ()
    permission_scope: RagPermissionScope | None = None
    top_k: int = 8
    candidate_limit: int = 80
    elastic_prefilter_limit: int = 1000


@dataclass(frozen=True, slots=True)
class RagRetrievalPipelineResult:
    candidates: tuple[RagRankedChunk, ...] = ()
    hard_gate: RagHardGateDecision | None = None
    direct_evidence: tuple[RagDirectEvidence, ...] = ()
    answerability_warning: RagAnswerabilityWarning | None = None
    graph_enhancement: RagGraphEnhancementResult = field(default_factory=RagGraphEnhancementResult)


class RagRetrievalPipeline:
    """组合 Elastic 前置过滤、Qdrant 主检索、ranking 后处理和 Neo4j 后置增强。"""

    __slots__ = (
        "_elastic_filter",
        "_embedding_client",
        "_evidence_materializer",
        "_graph_enhancement",
        "_hard_gate",
        "_qdrant_retriever",
        "_ranking_service",
        "_soft_gate",
    )

    def __init__(
            self,
            *,
            embedding_client: Any,
            elastic_filter: RagElasticFilter,
            qdrant_retriever: RagQdrantRetriever,
            ranking_service: RagEvidenceRankingService,
            hard_gate: AnswerabilityHardGate | None = None,
            soft_gate: AnswerabilitySoftGate | None = None,
            evidence_materializer: RagEvidenceMaterializer | None = None,
            graph_enhancement: RagGraphEnhancement | None = None,
    ) -> None:
        self._embedding_client = embedding_client
        self._elastic_filter = elastic_filter
        self._qdrant_retriever = qdrant_retriever
        self._ranking_service = ranking_service
        self._hard_gate = hard_gate
        self._soft_gate = soft_gate
        self._evidence_materializer = evidence_materializer
        self._graph_enhancement = graph_enhancement

    async def retrieve(self, request: RagRetrievalPipelineRequest) -> RagRetrievalPipelineResult:
        candidate_scope: tuple[str, ...] | None = None
        if request.keywords:
            candidate_scope = await self._elastic_filter.filter_candidate_chunk_ids(
                RagElasticKeywordFilterRequest(
                    keywords=request.keywords,
                    resource_id=request.resource_id,
                    permission_scope=request.permission_scope,
                    limit=request.elastic_prefilter_limit,
                )
            )
        # None 表示没有触发关键词过滤；空 tuple 表示 Elastic 已触发但没有命中，必须直接终止。
        if candidate_scope == ():
            return RagRetrievalPipelineResult(
                hard_gate=(
                    self._hard_gate.decide(_answerability_input(request, ()))
                    if self._hard_gate is not None
                    else None
                )
            )

        result = await self._embedding_client.aembed(request.query)
        query_vector = result.embeddings[0] if result.embeddings else []
        chunks = await self._qdrant_retriever.retrieve(
            RagQdrantRetrievalRequest(
                resource_id=request.resource_id,
                query_text=request.query,
                query_vector=query_vector,
                candidate_chunk_ids=candidate_scope or (),
                permission_scope=request.permission_scope,
                top_k=request.candidate_limit,
            )
        )
        ranking = await self._ranking_service.rank(
            RagEvidenceRankingRequest(
                query=request.query,
                chunks=chunks,
                top_k=request.top_k,
                candidate_limit=request.candidate_limit,
            )
        )
        candidates = _bind_ranked_chunks(
            ranked=ranking.ranked,
            chunks=chunks,
        )
        if (
                self._hard_gate is None
                or self._soft_gate is None
                or self._evidence_materializer is None
        ):
            return RagRetrievalPipelineResult(candidates=candidates)

        answerability_input = _answerability_input(request, candidates)
        hard_gate = self._hard_gate.decide(answerability_input)
        if not hard_gate.should_continue:
            return RagRetrievalPipelineResult(
                candidates=candidates,
                hard_gate=hard_gate,
            )

        direct_evidence = await self._evidence_materializer.materialize(
            _materialize_request(
                candidates=candidates,
                cache_scope=_build_materialization_cache_scope(request),
            )
        )
        warning = await self._soft_gate.evaluate(answerability_input)
        graph_enhancement = RagGraphEnhancementResult()
        if self._graph_enhancement is not None:
            graph_enhancement = await self._graph_enhancement.enhance(
                RagGraphEnhancementRequest(
                    query=request.query,
                    resource_id=request.resource_id,
                    direct_evidence=direct_evidence,
                    answerability_warning=warning,
                    permission_scope=request.permission_scope,
                )
            )
        return RagRetrievalPipelineResult(
            candidates=candidates,
            hard_gate=hard_gate,
            direct_evidence=direct_evidence,
            answerability_warning=warning,
            graph_enhancement=graph_enhancement,
        )


def _materialize_request(
        *,
        candidates: tuple[RagRankedChunk, ...],
        cache_scope: RagEvidenceMaterializationCacheScope | None,
):
    # materializer 依赖 retrieval 类型，放在运行时边界导入以避免 retrieval 包初始化环。
    from chat.application.rag.context_builder import RagEvidenceMaterializeRequest

    return RagEvidenceMaterializeRequest(
        candidates=candidates,
        cache_scope=cache_scope,
    )


def _answerability_input(
        request: RagRetrievalPipelineRequest,
        candidates: tuple[RagRankedChunk, ...],
) -> RagAnswerabilityInput:
    return RagAnswerabilityInput(
        query=request.query,
        retrieval_profile=request.retrieval_profile.value,
        ranked=tuple(item.ranking for item in candidates),
    )


def _bind_ranked_chunks(
        *,
        ranked: tuple[RankedCandidate, ...],
        chunks: tuple[ScoredChunk, ...],
) -> tuple[RagRankedChunk, ...]:
    # retrieval pipeline 内部完成排序结果和检索 payload 的对齐，下游只接触已排序候选。
    chunks_by_id = {
        chunk.chunk_id: chunk
        for chunk in chunks
    }
    return tuple(
        RagRankedChunk(
            ranking=item,
            chunk=chunk,
        )
        for item in ranked
        if (chunk := chunks_by_id.get(item.candidate_id)) is not None
    )


def _build_materialization_cache_scope(
        request: RagRetrievalPipelineRequest,
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
        permission_scope_key=_permission_scope_cache_key(request.permission_scope.group_role_map),
    )


def _permission_scope_cache_key(group_role_map: dict[str, str]) -> str:
    return "|".join(
        f"{group_id}:{role}"
        for group_id, role in sorted(group_role_map.items())
    )
