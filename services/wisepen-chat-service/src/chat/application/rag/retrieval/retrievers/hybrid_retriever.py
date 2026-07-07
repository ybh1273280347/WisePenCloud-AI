from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from chat.application.rag.retrieval.models import (
    RagElasticStrictPrefilterRequest,
    RagExactFilter,
    RagPermissionScope,
    RagQdrantRetrievalRequest,
    RagRetrievalProfile,
    ScoredChunk,
)
from .elastic_retriever import RagElasticRetriever
from .qdrant_retriever import RagQdrantRetriever


@dataclass(frozen=True, slots=True)
class RagHybridRetrievalRequest:
    query: str
    resource_id: str
    corpus_version: str
    retrieval_profile: RagRetrievalProfile = RagRetrievalProfile.BALANCED
    exact_filter: RagExactFilter | None = None
    permission_scope: RagPermissionScope | None = None
    candidate_limit: int = 100
    elastic_prefilter_limit: int = 1000


@dataclass(frozen=True, slots=True)
class RagHybridRetrievalResult:
    elastic_candidate_chunk_ids: tuple[str, ...] | None
    chunks: tuple[ScoredChunk, ...]


class RagHybridRetriever:
    """执行 Elastic strict prefilter + Qdrant dense/BM25 主召回。"""

    __slots__ = ("_elastic_retriever", "_embedding_client", "_qdrant_retriever")

    def __init__(
            self,
            *,
            embedding_client: Any,
            elastic_retriever: RagElasticRetriever,
            qdrant_retriever: RagQdrantRetriever,
    ) -> None:
        self._embedding_client = embedding_client
        self._elastic_retriever = elastic_retriever
        self._qdrant_retriever = qdrant_retriever

    async def retrieve(self, request: RagHybridRetrievalRequest) -> RagHybridRetrievalResult:
        candidate_scope = await self._resolve_elastic_candidate_scope(request)
        if candidate_scope == ():
            return RagHybridRetrievalResult(
                elastic_candidate_chunk_ids=(),
                chunks=(),
            )

        result = await self._embedding_client.aembed(request.query)
        query_vector = result.embeddings[0] if result.embeddings else []
        chunks = await self._qdrant_retriever.retrieve(
            RagQdrantRetrievalRequest(
                resource_id=request.resource_id,
                corpus_version=request.corpus_version,
                query_text=request.query,
                query_vector=query_vector,
                candidate_chunk_ids=candidate_scope or (),
                permission_scope=request.permission_scope,
                top_k=request.candidate_limit,
            )
        )
        return RagHybridRetrievalResult(
            elastic_candidate_chunk_ids=candidate_scope,
            chunks=chunks,
        )

    async def _resolve_elastic_candidate_scope(
            self,
            request: RagHybridRetrievalRequest,
    ) -> tuple[str, ...] | None:
        if not _should_use_elastic_prefilter(request):
            return None
        return await self._elastic_retriever.strict_prefilter(
            RagElasticStrictPrefilterRequest(
                query=request.query,
                resource_id=request.resource_id,
                corpus_version=request.corpus_version,
                exact_filter=request.exact_filter,
                permission_scope=request.permission_scope,
                limit=request.elastic_prefilter_limit,
            )
        )


def _should_use_elastic_prefilter(request: RagHybridRetrievalRequest) -> bool:
    return bool(
        request.retrieval_profile == RagRetrievalProfile.ANCHORED_EXACT
        or (
            request.exact_filter is not None
            and request.exact_filter.has_constraints
        )
    )
