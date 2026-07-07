from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client import models as qdrant_models

from chat.application.rag.retrieval.models import (
    RagQdrantRetrievalFilterRequest,
    RagQdrantRetrievalRequest,
    RagRetrievalChannel,
    ScoredChunk,
)
from chat.application.rag.retrieval.permission_filter import RagPermissionFilterBuilder


class RagQdrantRetriever:
    """Qdrant dense + BM25 主检索步骤。

    Qdrant filter 只承载 resource、Elastic 候选集合和 ACL 范围；内容相关性由 dense/BM25
    查询本身决定，不通过 payload 过滤表达。
    """

    __slots__ = (
        "_bm25_config",
        "_client",
        "_collection_name",
        "_dense_vector_name",
        "_permission_filter_builder",
        "_sparse_vector_name",
    )

    def __init__(
            self,
            *,
            client: AsyncQdrantClient | None,
            collection_name: str,
            permission_filter_builder: RagPermissionFilterBuilder,
            bm25_config: qdrant_models.Bm25Config,
            dense_vector_name: str = "dense",
            sparse_vector_name: str = "sparse",
    ) -> None:
        self._client = client
        self._collection_name = collection_name
        self._permission_filter_builder = permission_filter_builder
        self._bm25_config = bm25_config
        self._dense_vector_name = dense_vector_name
        self._sparse_vector_name = sparse_vector_name

    async def retrieve(self, request: RagQdrantRetrievalRequest) -> tuple[ScoredChunk, ...]:
        if self._client is None:
            return ()

        query_filter = self.build_retrieval_filter(
            RagQdrantRetrievalFilterRequest(
                resource_id=request.resource_id,
                candidate_chunk_ids=request.candidate_chunk_ids,
                permission_scope=request.permission_scope,
            )
        )
        channels = (
            (RagRetrievalChannel.DENSE, RagRetrievalChannel.SPARSE)
            if request.query_text.strip()
            else (RagRetrievalChannel.DENSE,)
        )
        response = await self._query_points(
            request=request,
            query_filter=query_filter,
        )
        return tuple(
            chunk
            for rank, point in enumerate(_read_response_points(response), start=1)
            if (chunk := _to_scored_chunk(point, rank=rank, channels=channels)) is not None
        )

    def build_retrieval_filter(
            self,
            request: RagQdrantRetrievalFilterRequest,
    ) -> qdrant_models.Filter:
        # candidate_chunk_ids 来自 Elastic 关键词 prefilter；没有关键词时不限制 chunk_id。
        must: list[qdrant_models.Condition] = [
            qdrant_models.FieldCondition(
                key="resource_id",
                match=qdrant_models.MatchValue(value=request.resource_id),
            ),
        ]
        if request.candidate_chunk_ids:
            must.append(
                qdrant_models.FieldCondition(
                    key="chunk_id",
                    match=qdrant_models.MatchAny(any=list(request.candidate_chunk_ids)),
                )
            )
        if request.permission_scope is not None:
            must.append(
                self._permission_filter_builder.build_qdrant_filter(request.permission_scope)
            )
        return qdrant_models.Filter(must=must)

    async def _query_points(
            self,
            *,
            request: RagQdrantRetrievalRequest,
            query_filter: qdrant_models.Filter,
    ) -> Any:
        if not request.query_text.strip():
            # 无文本查询时只能走 dense 向量；有文本时再启用 Qdrant BM25 sparse 分支做 RRF。
            return await self._client.query_points(
                collection_name=self._collection_name,
                query=list(request.query_vector),
                using=self._dense_vector_name,
                query_filter=query_filter,
                limit=request.top_k,
                with_payload=True,
            )

        return await self._client.query_points(
            collection_name=self._collection_name,
            prefetch=[
                qdrant_models.Prefetch(
                    query=list(request.query_vector),
                    using=self._dense_vector_name,
                    filter=query_filter,
                    limit=request.top_k,
                ),
                qdrant_models.Prefetch(
                    query=qdrant_models.Document(
                        text=request.query_text,
                        model="Qdrant/bm25",
                        options=self._bm25_config,
                    ),
                    using=self._sparse_vector_name,
                    filter=query_filter,
                    limit=request.top_k,
                ),
            ],
            query=qdrant_models.FusionQuery(fusion=qdrant_models.Fusion.RRF),
            limit=request.top_k,
            with_payload=True,
        )


def _read_response_points(response: Any) -> tuple[Any, ...]:
    points = getattr(response, "points", None)
    if points is not None:
        return tuple(points)
    if isinstance(response, Sequence) and not isinstance(response, (str, bytes, bytearray)):
        return tuple(response)
    return ()


def _to_scored_chunk(
        point: Any,
        *,
        rank: int,
        channels: tuple[RagRetrievalChannel, ...],
) -> ScoredChunk | None:
    payload = getattr(point, "payload", None)
    if not isinstance(payload, Mapping):
        return None

    chunk_id = _read_optional_payload_str(
        payload.get("chunk_id")
    ) or _read_optional_payload_str(
        getattr(point, "id", None)
    )
    if not chunk_id:
        return None

    parent_chunk_id = _read_optional_payload_str(payload.get("parent_chunk_id"))
    return ScoredChunk(
        chunk_id=chunk_id,
        text=_read_optional_payload_str(payload.get("evidence_text")) or "",
        retrieval_score=float(getattr(point, "score", 0.0)),
        retrieval_rank=rank,
        group_key=parent_chunk_id or None,
        resource_id=_read_optional_payload_str(payload.get("resource_id")) or "",
        document_version=_read_optional_payload_str(
            payload.get("document_version")
        ) or "",
        corpus_version=_read_optional_payload_str(payload.get("corpus_version")) or "",
        parent_chunk_id=parent_chunk_id or "",
        page_label=_read_optional_payload_str(payload.get("page_label")),
        section_path=_read_payload_str_sequence(payload.get("section_path")),
        anchor_labels=_read_payload_str_sequence(payload.get("anchor_labels")),
        retrieval_channels=channels,
    )


def _read_optional_payload_str(value: object) -> str | None:
    if value is None:
        return None
    candidate = str(value).strip()
    return candidate or None


def _read_payload_str_sequence(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return ()
    return tuple(
        candidate
        for item in value
        if (candidate := str(item).strip())
    )
