from __future__ import annotations

import asyncio
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
from chat.core.persistence._utils.payload_readers import (
    read_optional_trimmed_str,
    read_trimmed_str_sequence,
)

_RETRIEVAL_PAYLOAD_FIELDS = (
    "chunk_id",
    "evidence_text",
    "resource_id",
    "document_version",
    "corpus_version",
    "parent_chunk_id",
    "page_label",
    "section_path",
    "anchor_labels",
)


@dataclass(frozen=True, slots=True)
class _RetrievedPoint:
    point: qdrant_types.ScoredPoint
    score: float
    channels: tuple[RagRetrievalChannel, ...]
    signals: tuple[RagRetrievalSignal, ...]


class RagQdrantRetriever:
    """在 resource、Elastic 候选和 ACL 范围内执行 dense + BM25 主检索。"""

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

    async def retrieve(
        self,
        request: RagQdrantRetrievalRequest,
    ) -> tuple[ScoredChunk, ...]:
        client = self._client
        if client is None or request.top_k <= 0:
            return ()

        points = await self._query_points(
            client=client,
            request=request,
            query_filter=self.build_retrieval_filter(
                RagQdrantRetrievalFilterRequest(
                    resource_id=request.resource_id,
                    candidate_chunk_ids=request.candidate_chunk_ids,
                    permission_scope=request.permission_scope,
                )
            ),
        )

        chunks: list[ScoredChunk] = []
        for item in points:
            chunk = _to_scored_chunk(
                item.point,
                rank=len(chunks) + 1,
                retrieval_score=item.score,
                channels=item.channels,
                signals=item.signals,
            )
            if chunk is not None:
                chunks.append(chunk)
        return tuple(chunks)

    def build_retrieval_filter(
        self,
        request: RagQdrantRetrievalFilterRequest,
    ) -> qdrant_models.Filter:
        """构造仅用于限定 resource、Elastic 候选和 ACL 的 Qdrant filter。"""
        must: list[qdrant_models.Condition] = [
            qdrant_models.FieldCondition(
                key="resource_id",
                match=qdrant_models.MatchValue(value=request.resource_id),
            )
        ]

        if request.candidate_chunk_ids:
            candidate_ids = list(dict.fromkeys(
                chunk_id.strip()
                for chunk_id in request.candidate_chunk_ids
                if chunk_id.strip()
            ))
            # 输入声明存在候选集合时保持 fail-closed，不能因脏数据退化为全资源检索。
            must.append(
                qdrant_models.FieldCondition(
                    key="chunk_id",
                    match=qdrant_models.MatchAny(any=candidate_ids or [""]),
                )
            )

        if request.permission_scope is not None:
            must.append(
                self._permission_filter_builder.build_qdrant_filter(
                    request.permission_scope
                )
            )
        return qdrant_models.Filter(must=must)

    async def _query_points(
        self,
        *,
        client: AsyncQdrantClient,
        request: RagQdrantRetrievalRequest,
        query_filter: qdrant_models.Filter,
    ) -> tuple[_RetrievedPoint, ...]:
        query_text = request.query_text.strip()
        query_vector = list(request.query_vector)
        if query_vector and query_text:
            dense_response, sparse_response = await asyncio.gather(
                client.query_points(
                    collection_name=self._collection_name,
                    query=query_vector,
                    using=self._dense_vector_name,
                    query_filter=query_filter,
                    limit=request.top_k,
                    with_payload=list(_RETRIEVAL_PAYLOAD_FIELDS),
                ),
                client.query_points(
                    collection_name=self._collection_name,
                    query=qdrant_models.Document(
                        text=query_text,
                        model="Qdrant/bm25",
                        options=self._bm25_config,
                    ),
                    using=self._sparse_vector_name,
                    query_filter=query_filter,
                    limit=request.top_k,
                    with_payload=list(_RETRIEVAL_PAYLOAD_FIELDS),
                ),
            )
            return _merge_channel_points(
                dense_points=tuple(dense_response.points),
                sparse_points=tuple(sparse_response.points),
            )

        if query_vector:
            channel = RagRetrievalChannel.DENSE
            response = await client.query_points(
                collection_name=self._collection_name,
                query=query_vector,
                using=self._dense_vector_name,
                query_filter=query_filter,
                limit=request.top_k,
                with_payload=list(_RETRIEVAL_PAYLOAD_FIELDS),
            )
        elif query_text:
            channel = RagRetrievalChannel.SPARSE
            response = await client.query_points(
                collection_name=self._collection_name,
                query=qdrant_models.Document(
                    text=query_text,
                    model="Qdrant/bm25",
                    options=self._bm25_config,
                ),
                using=self._sparse_vector_name,
                query_filter=query_filter,
                limit=request.top_k,
                with_payload=list(_RETRIEVAL_PAYLOAD_FIELDS),
            )
        else:
            return ()

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
    """按首次出现顺序合并通道，并保留每个通道的原始 rank/score 信号。"""
    merged: dict[str, _RetrievedPoint] = {}

    for channel, points in (
        (RagRetrievalChannel.DENSE, dense_points),
        (RagRetrievalChannel.SPARSE, sparse_points),
    ):
        for rank, point in enumerate(points, start=1):
            chunk_id = read_optional_trimmed_str(
                (point.payload or {}).get("chunk_id")
            ) or read_optional_trimmed_str(point.id)
            if not chunk_id:
                continue

            signal = RagRetrievalSignal(
                channel=channel,
                rank=rank,
                score=point.score,
            )
            existing = merged.get(chunk_id)
            if existing is None:
                merged[chunk_id] = _RetrievedPoint(
                    point=point,
                    score=point.score,
                    channels=(channel,),
                    signals=(signal,),
                )
                continue

            merged[chunk_id] = _RetrievedPoint(
                point=existing.point,
                score=max(existing.score, point.score),
                channels=(
                    existing.channels
                    if channel in existing.channels
                    else (*existing.channels, channel)
                ),
                signals=(*existing.signals, signal),
            )

    return tuple(merged.values())


def _to_scored_chunk(
    point: qdrant_types.ScoredPoint,
    *,
    rank: int,
    retrieval_score: float,
    channels: tuple[RagRetrievalChannel, ...],
    signals: tuple[RagRetrievalSignal, ...],
) -> ScoredChunk | None:
    payload = point.payload or {}
    chunk_id = read_optional_trimmed_str(
        payload.get("chunk_id")
    ) or read_optional_trimmed_str(point.id)
    if not chunk_id:
        return None

    parent_chunk_id = read_optional_trimmed_str(payload.get("parent_chunk_id")) or ""
    return ScoredChunk(
        chunk_id=chunk_id,
        text=read_optional_trimmed_str(payload.get("evidence_text")) or "",
        retrieval_score=retrieval_score,
        retrieval_rank=rank,
        group_key=parent_chunk_id or None,
        resource_id=read_optional_trimmed_str(payload.get("resource_id")) or "",
        document_version=read_optional_trimmed_str(
            payload.get("document_version")
        ) or "",
        corpus_version=read_optional_trimmed_str(payload.get("corpus_version")) or "",
        parent_chunk_id=parent_chunk_id,
        page_label=read_optional_trimmed_str(payload.get("page_label")),
        section_path=read_trimmed_str_sequence(payload.get("section_path")),
        anchor_labels=read_trimmed_str_sequence(payload.get("anchor_labels")),
        retrieval_channels=channels,
        retrieval_signals=signals,
    )
