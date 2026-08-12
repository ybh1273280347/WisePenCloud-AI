"""Qdrant dense/BM25 混合候选召回 adapter。"""

from collections.abc import Mapping

from qdrant_client import AsyncQdrantClient
from qdrant_client import models as qdrant_models

from rag.core.persistence.qdrant.acl_filter import permission_filter
from rag.core.persistence.qdrant.mappers.deserializer import to_retrieval_candidate
from rag.domain.repositories.candidate_search import CandidateSearch
from rag.domain.retrieval import CandidateSearchRequest, RetrievalCandidate


class QdrantCandidateSearch(CandidateSearch):
    """仅执行 Qdrant 召回和候选 payload 映射，不做应用层排序或核验。"""

    def __init__(
        self,
        *,
        client: AsyncQdrantClient,
        collection_name: str,
        dense_vector_name: str,
        sparse_vector_name: str,
        bm25_options: Mapping[str, object] | None = None,
        dense_vector_size: int | None = None,
    ) -> None:
        if not collection_name.strip():
            raise ValueError("collection_name must not be empty")
        if not dense_vector_name.strip() or not sparse_vector_name.strip():
            raise ValueError("vector names must not be empty")
        if dense_vector_size is not None and dense_vector_size <= 0:
            raise ValueError("dense_vector_size must be positive")
        self._client = client
        self._collection_name = collection_name
        self._dense_vector_name = dense_vector_name
        self._sparse_vector_name = sparse_vector_name
        self._bm25_options = dict(bm25_options or {})
        self._dense_vector_size = dense_vector_size

    async def search(self, request: CandidateSearchRequest) -> list[RetrievalCandidate]:
        if request.limit <= 0:
            return []
        if not await self._client.collection_exists(self._collection_name):
            return []
        if not request.lexical_query.strip():
            raise ValueError("lexical_query must not be empty")
        if not request.semantic_vector:
            raise ValueError("semantic_vector must not be empty")
        if (
            self._dense_vector_size is not None
            and len(request.semantic_vector) != self._dense_vector_size
        ):
            raise ValueError("semantic_vector size does not match collection")

        query_filter = self._build_filter(request)
        response = await self._client.query_points(
            collection_name=self._collection_name,
            prefetch=[
                qdrant_models.Prefetch(
                    query=list(request.semantic_vector),
                    using=self._dense_vector_name,
                    filter=query_filter,
                    limit=request.limit,
                ),
                qdrant_models.Prefetch(
                    query=qdrant_models.Document(
                        text=request.lexical_query,
                        model="qdrant/bm25",
                        options=self._bm25_options or None,
                    ),
                    using=self._sparse_vector_name,
                    filter=query_filter,
                    limit=request.limit,
                ),
            ],
            query=qdrant_models.FusionQuery(fusion=qdrant_models.Fusion.RRF),
            query_filter=query_filter,
            limit=request.limit,
            with_payload=_PAYLOAD_FIELDS,
        )
        return [
            to_retrieval_candidate(point.payload, score=point.score)
            for point in response.points
        ]

    @staticmethod
    def _build_filter(request: CandidateSearchRequest) -> qdrant_models.Filter:
        must: list[qdrant_models.Condition] = [
            qdrant_models.FieldCondition(
                key="active",
                match=qdrant_models.MatchValue(value=True),
            ),
            permission_filter(request.permission_scope),
        ]
        resource_ids = list(dict.fromkeys(request.resource_ids))
        if resource_ids:
            must.append(
                qdrant_models.FieldCondition(
                    key="resource_id",
                    match=qdrant_models.MatchAny(any=resource_ids),
                )
            )
        return qdrant_models.Filter(must=must)


_PAYLOAD_FIELDS = [
    "content_revision",
    "resource_id",
    "chunk_id",
    "reading_block_id",
    "raw_text",
    "section_id",
    "section_path",
    "anchor_labels",
    "source_ref_id",
]
