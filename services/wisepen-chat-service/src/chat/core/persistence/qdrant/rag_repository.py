from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import AsyncQdrantClient
from qdrant_client import models as qdrant_models

from chat.application.rag.acl import RagResourceAclProjection

_DEFAULT_DENSE_VECTOR_NAME = "dense"
_DEFAULT_SPARSE_VECTOR_NAME = "sparse"
_QDRANT_BM25_MODEL = "Qdrant/bm25"


class RagQdrantRepository:
    """RAG child chunk 的 Qdrant 检索投影仓储。"""

    __slots__ = (
        "_client",
        "_collection_name",
        "_collection_ready",
        "_dense_vector_name",
        "_dense_vector_size",
        "_bm25_config",
        "_sparse_vector_name",
    )

    def __init__(
            self,
            *,
            client: AsyncQdrantClient | None,
            collection_name: str,
            dense_vector_size: int,
            bm25_config: qdrant_models.Bm25Config,
            dense_vector_name: str = _DEFAULT_DENSE_VECTOR_NAME,
            sparse_vector_name: str = _DEFAULT_SPARSE_VECTOR_NAME,
    ) -> None:
        self._client = client
        self._collection_name = collection_name
        self._dense_vector_name = dense_vector_name
        self._sparse_vector_name = sparse_vector_name
        self._dense_vector_size = dense_vector_size
        self._bm25_config = bm25_config
        self._collection_ready = False

    async def upsert_child_chunks(
            self,
            *,
            child_chunks: tuple[Any, ...],
            dense_vectors: Mapping[str, Sequence[float]],
            resource_id: str,
            document_version: str,
            corpus_version: str,
            acl_projection: RagResourceAclProjection | None = None,
    ) -> None:
        if self._client is None:
            return
        if not child_chunks:
            if await self._client.collection_exists(self._collection_name):
                await self._delete_document_points(
                    resource_id=resource_id,
                    document_version=document_version,
                )
            return

        await self.ensure_collection()
        await self._delete_document_points(
            resource_id=resource_id,
            document_version=document_version,
        )
        points = [
            qdrant_models.PointStruct(
                id=str(_point_id(child.chunk_id)),
                vector=self._build_vector(
                    child,
                    dense_vectors=dense_vectors,
                ),
                payload=self._build_child_payload(
                    child,
                    resource_id=resource_id,
                    document_version=document_version,
                    corpus_version=corpus_version,
                    acl_projection=acl_projection,
                ),
            )
            for child in child_chunks
        ]
        await self._client.upsert(
            collection_name=self._collection_name,
            points=points,
            wait=True,
        )

    async def ensure_collection(self) -> None:
        if self._client is None or self._collection_ready:
            return
        if self._dense_vector_size <= 0:
            return

        dense_config = {
            self._dense_vector_name: qdrant_models.VectorParams(
                size=self._dense_vector_size,
                distance=qdrant_models.Distance.COSINE,
            )
        }
        sparse_config = {
            self._sparse_vector_name: qdrant_models.SparseVectorParams(
                modifier=qdrant_models.Modifier.IDF,
            )
        }
        if await self._client.collection_exists(self._collection_name):
            await self._client.update_collection(
                collection_name=self._collection_name,
                sparse_vectors_config=sparse_config,
            )
        else:
            await self._client.create_collection(
                collection_name=self._collection_name,
                vectors_config=dense_config,
                sparse_vectors_config=sparse_config,
            )
        self._collection_ready = True

    async def _delete_document_points(
            self,
            *,
            resource_id: str,
            document_version: str,
    ) -> None:
        await self._client.delete(
            collection_name=self._collection_name,
            points_selector=qdrant_models.FilterSelector(
                filter=qdrant_models.Filter(
                    must=[
                        qdrant_models.FieldCondition(
                            key="resource_id",
                            match=qdrant_models.MatchValue(value=resource_id),
                        ),
                        qdrant_models.FieldCondition(
                            key="document_version",
                            match=qdrant_models.MatchValue(value=document_version),
                        ),
                    ]
                )
            ),
            wait=True,
        )

    async def update_acl_projection(self, projection: RagResourceAclProjection) -> None:
        if self._client is None:
            return

        await self._client.set_payload(
            collection_name=self._collection_name,
            payload=_build_acl_payload(projection),
            points=qdrant_models.Filter(
                must=[
                    qdrant_models.FieldCondition(
                        key="resource_id",
                        match=qdrant_models.MatchValue(value=projection.resource_id),
                    )
                ]
            ),
            wait=True,
        )

    def _build_vector(
            self,
            child: Any,
            *,
            dense_vectors: Mapping[str, Sequence[float]],
    ) -> dict[str, Any]:
        return {
            self._dense_vector_name: list(dense_vectors[child.chunk_id]),
            self._sparse_vector_name: qdrant_models.Document(
                text=child.indexing_text or child.text,
                model=_QDRANT_BM25_MODEL,
                options=self._bm25_config,
            ),
        }

    def _build_child_payload(
            self,
            child: Any,
            *,
            resource_id: str,
            document_version: str,
            corpus_version: str,
            acl_projection: RagResourceAclProjection | None,
    ) -> dict[str, Any]:
        payload = {
            "chunk_id": child.chunk_id,
            "parent_chunk_id": child.parent_chunk_id,
            "resource_id": resource_id,
            "document_version": document_version,
            "corpus_version": corpus_version,
            "content_hash": child.content_hash,
            "evidence_text": child.text,
            "page_label": child.page_label,
            "section_path": list(child.section_path),
            "anchor_labels": list(child.anchor_labels),
            "start_offset": child.start_offset,
            "end_offset": child.end_offset,
        }
        if acl_projection is None:
            return payload

        payload.update(_build_acl_payload(acl_projection))
        return payload


def _build_acl_payload(projection: RagResourceAclProjection) -> dict[str, Any]:
    return {
        "owner_id": projection.owner_id,
        "readable_users": list(projection.readable_users),
        "computed_group_acls": [
            {
                "group_id": item.group_id,
                "is_readable": item.is_readable,
                "readable_users": list(item.readable_users),
                "excluded_read_users": list(item.excluded_read_users),
            }
            for item in projection.computed_group_acls
        ],
    }


def _point_id(chunk_id: str) -> Any:
    return uuid5(NAMESPACE_URL, f"wisepen-rag-child-chunk:{chunk_id}")
