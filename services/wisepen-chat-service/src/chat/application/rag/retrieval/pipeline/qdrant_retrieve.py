from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass

from qdrant_client import AsyncQdrantClient
from qdrant_client import models as qdrant_models
from qdrant_client.conversions import common_types as qdrant_types

from chat.application.rag.retrieval.models import (
    RagQdrantRetrievalFilterRequest,
    RagQdrantRetrievalRequest,
    RagRetrievalChannel,
    RagRetrievalSignal,
    ScoredChunk,
)
from chat.application.rag.retrieval.permission_filter import RagPermissionFilterBuilder


@dataclass(frozen=True, slots=True)
class _RetrievedPoint:
    point: qdrant_types.ScoredPoint
    score: float
    channels: tuple[RagRetrievalChannel, ...]
    signals: tuple[RagRetrievalSignal, ...]


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
        points = await self._query_points(
            request=request,
            query_filter=query_filter,
        )
        return tuple(
            chunk
            for rank, item in enumerate(points, start=1)
            if (
                chunk := _to_scored_chunk(
                    item.point,
                    rank=rank,
                    retrieval_score=item.score,
                    channels=item.channels,
                    signals=item.signals,
                )
            ) is not None
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
    ) -> tuple[_RetrievedPoint, ...]:
        # ---- 无文本退化：只有向量可走 ----
        if not request.query_text.strip():
            return _wrap_response_points(
                await self._query_dense_points(
                    request=request,
                    query_filter=query_filter,
                ),
                channel=RagRetrievalChannel.DENSE,
            )

        dense_response, sparse_response = await asyncio.gather(
            self._query_dense_points(request=request, query_filter=query_filter),
            self._query_sparse_points(request=request, query_filter=query_filter),
        )
        return _merge_channel_points(
            dense_points=tuple(dense_response.points),
            sparse_points=tuple(sparse_response.points),
        )

    async def _query_dense_points(
            self,
            *,
            request: RagQdrantRetrievalRequest,
            query_filter: qdrant_models.Filter,
    ) -> qdrant_types.QueryResponse:
        return await self._client.query_points(
            collection_name=self._collection_name,
            query=list(request.query_vector),
            using=self._dense_vector_name,
            query_filter=query_filter,
            limit=request.top_k,
            with_payload=True,
        )

    async def _query_sparse_points(
            self,
            *,
            request: RagQdrantRetrievalRequest,
            query_filter: qdrant_models.Filter,
    ) -> qdrant_types.QueryResponse:
        return await self._client.query_points(
            collection_name=self._collection_name,
            query=qdrant_models.Document(
                text=request.query_text,
                model="Qdrant/bm25",
                options=self._bm25_config,
            ),
            using=self._sparse_vector_name,
            query_filter=query_filter,
            limit=request.top_k,
            with_payload=True,
        )


def _wrap_response_points(
        response: qdrant_types.QueryResponse,
        *,
        channel: RagRetrievalChannel,
) -> tuple[_RetrievedPoint, ...]:
    return tuple(
        _RetrievedPoint(
            point=point,
            score=point.score,
            channels=(channel,),
            signals=(
                RagRetrievalSignal(
                    channel=channel,
                    rank=rank,
                    score=point.score,
                ),
            ),
        )
        for rank, point in enumerate(response.points, start=1)
    )


def _merge_channel_points(
        *,
        dense_points: tuple[qdrant_types.ScoredPoint, ...],
        sparse_points: tuple[qdrant_types.ScoredPoint, ...],
) -> tuple[_RetrievedPoint, ...]:
    points_by_chunk_id: dict[str, qdrant_types.ScoredPoint] = {}
    scores_by_chunk_id: dict[str, float] = {}
    channels_by_chunk_id: dict[str, set[RagRetrievalChannel]] = {}
    signals_by_chunk_id: dict[str, list[RagRetrievalSignal]] = {}
    first_seen_order: dict[str, int] = {}

    for channel, points in (
            (RagRetrievalChannel.DENSE, dense_points),
            (RagRetrievalChannel.SPARSE, sparse_points),
    ):
        for rank, point in enumerate(points, start=1):
            chunk_id = _read_optional_payload_str(
                (point.payload or {}).get("chunk_id"),
            ) or _read_optional_payload_str(point.id)

            if not chunk_id:
                continue

            if chunk_id not in first_seen_order:
                first_seen_order[chunk_id] = len(first_seen_order)
                points_by_chunk_id[chunk_id] = point
                scores_by_chunk_id[chunk_id] = 0.0
                channels_by_chunk_id[chunk_id] = set()
                signals_by_chunk_id[chunk_id] = []

            scores_by_chunk_id[chunk_id] = max(scores_by_chunk_id[chunk_id], point.score)
            channels_by_chunk_id[chunk_id].add(channel)
            signals_by_chunk_id[chunk_id].append(
                RagRetrievalSignal(
                    channel=channel,
                    rank=rank,
                    score=point.score,
                )
            )

    return tuple(
        _RetrievedPoint(
            point=points_by_chunk_id[chunk_id],
            score=scores_by_chunk_id[chunk_id],
            channels=tuple(
                channel
                for channel in (RagRetrievalChannel.DENSE, RagRetrievalChannel.SPARSE)
                if channel in channels_by_chunk_id[chunk_id]
            ),
            signals=tuple(signals_by_chunk_id[chunk_id]),
        )
        for chunk_id in sorted(
            scores_by_chunk_id,
            key=lambda item: first_seen_order[item],
        )
    )


def _to_scored_chunk(
        point: qdrant_types.ScoredPoint,
        *,
        rank: int,
        retrieval_score: float,
        channels: tuple[RagRetrievalChannel, ...],
        signals: tuple[RagRetrievalSignal, ...],
) -> ScoredChunk | None:
    payload = point.payload or {}
    chunk_id = _read_optional_payload_str(
        payload.get("chunk_id")
    ) or _read_optional_payload_str(
        point.id
    )
    if not chunk_id:
        return None

    parent_chunk_id = _read_optional_payload_str(payload.get("parent_chunk_id"))
    return ScoredChunk(
        chunk_id=chunk_id,
        text=_read_optional_payload_str(payload.get("evidence_text")) or "",
        retrieval_score=retrieval_score,
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
        retrieval_signals=signals,
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
