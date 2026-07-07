from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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


@dataclass(frozen=True, slots=True)
class RagRetrievalPipelineRequest:
    query: str
    resource_id: str
    retrieval_profile: RagRetrievalProfile = RagRetrievalProfile.BALANCED
    keywords: tuple[str, ...] = ()
    permission_scope: RagPermissionScope | None = None
    top_k: int = 8
    candidate_limit: int = 80
    elastic_prefilter_limit: int = 1000


@dataclass(frozen=True, slots=True)
class RagRetrievalPipelineResult:
    candidates: tuple[RagRankedChunk, ...] = ()


class RagRetrievalPipeline:
    """组合 Elastic 前置过滤、Qdrant 主检索、ranking 后处理和 Neo4j 后置增强。"""

    __slots__ = (
        "_elastic_filter",
        "_embedding_client",
        "_graph_enhancement",
        "_qdrant_retriever",
        "_ranking_service",
    )

    def __init__(
            self,
            *,
            embedding_client: Any,
            elastic_filter: RagElasticFilter,
            qdrant_retriever: RagQdrantRetriever,
            ranking_service: RagEvidenceRankingService,
            graph_enhancement: RagGraphEnhancement | None = None,
    ) -> None:
        self._embedding_client = embedding_client
        self._elastic_filter = elastic_filter
        self._qdrant_retriever = qdrant_retriever
        self._ranking_service = ranking_service
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
            return RagRetrievalPipelineResult()

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
        return RagRetrievalPipelineResult(
            candidates=_bind_ranked_chunks(
                ranked=ranking.ranked,
                chunks=chunks,
            ),
        )

    async def enhance_graph(
            self,
            request: RagGraphEnhancementRequest,
    ) -> RagGraphEnhancementResult:
        if self._graph_enhancement is None:
            return RagGraphEnhancementResult()
        return await self._graph_enhancement.enhance(request)


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
