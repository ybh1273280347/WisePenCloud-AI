"""Qdrant retrieval index 的写入 adapter。"""

import asyncio
from collections.abc import Mapping, Sequence
from hashlib import sha256
from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client import models as qdrant_models

from rag.core.persistence.qdrant.mappers.serializer import (
    retrieval_point_id,
    retrieval_point_payload,
)
from rag.domain.acl import ResourceAcl
from rag.domain.repositories.retrieval_index_writer import RetrievalIndexWriter
from rag.domain.retrieval import RetrievalChunk, SourceRef


class QdrantRetrievalIndexWriter(RetrievalIndexWriter):
    """写入 staged retrieval points，并按 revision 控制召回可见性。"""

    def __init__(
        self,
        *,
        client: AsyncQdrantClient,
        collection_name: str,
        dense_vector_size: int,
        embedding_profile: str,
        dense_vector_name: str = "dense",
        sparse_vector_name: str = "sparse",
        bm25_options: Mapping[str, Any] | None = None,
    ) -> None:
        if dense_vector_size <= 0:
            raise ValueError("dense_vector_size must be positive")
        if not collection_name.strip():
            raise ValueError("collection_name must not be empty")
        if not embedding_profile.strip():
            raise ValueError("embedding_profile must not be empty")
        if not dense_vector_name.strip() or not sparse_vector_name.strip():
            raise ValueError("vector names must not be empty")

        self._client = client
        self._collection_name = collection_name
        self._dense_vector_size = dense_vector_size
        self._embedding_profile = embedding_profile.strip()
        self._dense_vector_name = dense_vector_name
        self._sparse_vector_name = sparse_vector_name
        self._bm25_options = dict(bm25_options or {})
        self._collection_lock = asyncio.Lock()
        self._collection_ready = False

    async def load_reusable_vectors(
        self,
        *,
        resource_id: str,
        chunks: Sequence[RetrievalChunk],
    ) -> dict[str, list[float]]:
        if not chunks or not await self._client.collection_exists(self._collection_name):
            return {}

        chunk_keys = {
            chunk.chunk_id: self._embedding_key(chunk.index_text) for chunk in chunks
        }
        vectors_by_key: dict[str, list[float]] = {}
        offset = None
        while True:
            records, offset = await self._client.scroll(
                collection_name=self._collection_name,
                scroll_filter=qdrant_models.Filter(
                    must=[
                        _match("resource_id", resource_id),
                        qdrant_models.FieldCondition(
                            key="embedding_key",
                            match=qdrant_models.MatchAny(
                                any=list(dict.fromkeys(chunk_keys.values()))
                            ),
                        ),
                    ]
                ),
                limit=256,
                offset=offset,
                with_payload=["embedding_key"],
                with_vectors=[self._dense_vector_name],
            )
            for record in records:
                payload = record.payload or {}
                embedding_key = payload.get("embedding_key")
                vectors = record.vector
                vector = (
                    vectors.get(self._dense_vector_name)
                    if isinstance(vectors, Mapping)
                    else None
                )
                if (
                    isinstance(embedding_key, str)
                    and isinstance(vector, Sequence)
                    and not isinstance(vector, (str, bytes))
                    and len(vector) == self._dense_vector_size
                ):
                    vectors_by_key.setdefault(embedding_key, list(vector))
            if offset is None:
                break

        return {
            chunk_id: vectors_by_key[embedding_key]
            for chunk_id, embedding_key in chunk_keys.items()
            if embedding_key in vectors_by_key
        }

    async def write_staged_revision(
        self,
        *,
        resource_id: str,
        content_revision: str,
        chunks: Sequence[RetrievalChunk],
        source_refs: Sequence[SourceRef],
        dense_vectors: Mapping[str, Sequence[float]],
        resource_acl: ResourceAcl,
    ) -> None:
        if not chunks:
            return
        if resource_acl.resource_id != resource_id:
            raise ValueError("resource ACL does not match resource")

        source_refs_by_chunk = _source_refs_by_chunk(
            resource_id=resource_id,
            content_revision=content_revision,
            source_refs=source_refs,
        )
        await self.ensure_collection()

        points = []
        chunk_ids: set[str] = set()
        for chunk in chunks:
            if chunk.chunk_id in chunk_ids:
                raise ValueError(f"chunks contain duplicate chunk {chunk.chunk_id}")
            chunk_ids.add(chunk.chunk_id)
            source_ref = source_refs_by_chunk.get(chunk.chunk_id)
            if source_ref is None:
                raise ValueError(f"source ref is missing for chunk {chunk.chunk_id}")
            vector = dense_vectors.get(chunk.chunk_id)
            if vector is None:
                raise ValueError(f"dense vector is missing for chunk {chunk.chunk_id}")
            if len(vector) != self._dense_vector_size:
                raise ValueError(f"dense vector size does not match chunk {chunk.chunk_id}")

            points.append(
                qdrant_models.PointStruct(
                    id=retrieval_point_id(content_revision, chunk.chunk_id),
                    vector={
                        self._dense_vector_name: list(vector),
                        self._sparse_vector_name: qdrant_models.Document(
                            text=chunk.index_text,
                            model="qdrant/bm25",
                            options=self._bm25_options or None,
                        ),
                    },
                    payload=retrieval_point_payload(
                        resource_id=resource_id,
                        content_revision=content_revision,
                        chunk=chunk,
                        source_ref=source_ref,
                        embedding_key=self._embedding_key(chunk.index_text),
                        resource_acl=resource_acl,
                        active=False,
                    ),
                )
            )

        await self._client.upsert(
            collection_name=self._collection_name,
            points=points,
            wait=True,
        )

    async def activate_revision(
        self,
        *,
        resource_id: str,
        content_revision: str,
    ) -> None:
        if not await self._client.collection_exists(self._collection_name):
            return

        await self._client.set_payload(
            collection_name=self._collection_name,
            payload={"active": True},
            points=qdrant_models.Filter(
                must=[
                    _match("resource_id", resource_id),
                    _match("content_revision", content_revision),
                ]
            ),
            wait=True,
        )
        # 先关闭旧 revision 的召回可见性，再由清理步骤删除其 points。
        await self._client.set_payload(
            collection_name=self._collection_name,
            payload={"active": False},
            points=qdrant_models.Filter(
                must=[_match("resource_id", resource_id)],
                must_not=[_match("content_revision", content_revision)],
            ),
            wait=True,
        )

    async def delete_other_revisions(
        self,
        *,
        resource_id: str,
        keep_content_revision: str,
    ) -> None:
        if not await self._client.collection_exists(self._collection_name):
            return
        await self._client.delete(
            collection_name=self._collection_name,
            points_selector=qdrant_models.FilterSelector(
                filter=qdrant_models.Filter(
                    must=[_match("resource_id", resource_id)],
                    must_not=[_match("content_revision", keep_content_revision)],
                )
            ),
            wait=True,
        )

    async def delete_resources(self, resource_ids: Sequence[str]) -> None:
        ids = list(dict.fromkeys(resource_ids))
        if not ids or not await self._client.collection_exists(self._collection_name):
            return
        await self._client.delete(
            collection_name=self._collection_name,
            points_selector=qdrant_models.FilterSelector(
                filter=qdrant_models.Filter(
                    must=[
                        qdrant_models.FieldCondition(
                            key="resource_id",
                            match=qdrant_models.MatchAny(any=ids),
                        )
                    ]
                )
            ),
            wait=True,
        )

    async def ensure_collection(self) -> None:
        if self._collection_ready:
            return
        async with self._collection_lock:
            if self._collection_ready:
                return
            if not await self._client.collection_exists(self._collection_name):
                await self._client.create_collection(
                    collection_name=self._collection_name,
                    vectors_config={
                        self._dense_vector_name: qdrant_models.VectorParams(
                            size=self._dense_vector_size,
                            distance=qdrant_models.Distance.COSINE,
                        )
                    },
                    sparse_vectors_config={
                        self._sparse_vector_name: qdrant_models.SparseVectorParams(
                            modifier=qdrant_models.Modifier.IDF,
                        )
                    },
                )
            for field_name, field_schema in _payload_indexes():
                await self._client.create_payload_index(
                    collection_name=self._collection_name,
                    field_name=field_name,
                    field_schema=field_schema,
                    wait=True,
                )
            self._collection_ready = True

    def _embedding_key(self, index_text: str) -> str:
        return sha256(
            f"{self._embedding_profile}\0{index_text}".encode()
        ).hexdigest()


def _source_refs_by_chunk(
    *,
    resource_id: str,
    content_revision: str,
    source_refs: Sequence[SourceRef],
) -> dict[str, SourceRef]:
    refs_by_chunk: dict[str, SourceRef] = {}
    for source_ref in source_refs:
        if (
            source_ref.resource_id != resource_id
            or source_ref.content_revision != content_revision
        ):
            raise ValueError(f"source ref {source_ref.ref_id} does not belong to revision")
        if source_ref.chunk_id in refs_by_chunk:
            raise ValueError(f"source refs contain duplicate chunk {source_ref.chunk_id}")
        refs_by_chunk[source_ref.chunk_id] = source_ref
    return refs_by_chunk


def _payload_indexes() -> tuple[tuple[str, qdrant_models.PayloadSchemaType], ...]:
    return (
        ("resource_id", qdrant_models.PayloadSchemaType.KEYWORD),
        ("content_revision", qdrant_models.PayloadSchemaType.KEYWORD),
        ("active", qdrant_models.PayloadSchemaType.BOOL),
        ("embedding_key", qdrant_models.PayloadSchemaType.KEYWORD),
        ("acl_revision", qdrant_models.PayloadSchemaType.INTEGER),
        ("owner_id", qdrant_models.PayloadSchemaType.KEYWORD),
        ("readable_users", qdrant_models.PayloadSchemaType.KEYWORD),
        ("excluded_read_users", qdrant_models.PayloadSchemaType.KEYWORD),
        ("group_acls[].group_id", qdrant_models.PayloadSchemaType.KEYWORD),
        ("group_acls[].is_readable", qdrant_models.PayloadSchemaType.BOOL),
        ("group_acls[].readable_users", qdrant_models.PayloadSchemaType.KEYWORD),
        ("group_acls[].excluded_read_users", qdrant_models.PayloadSchemaType.KEYWORD),
    )


def _match(key: str, value: str) -> qdrant_models.FieldCondition:
    return qdrant_models.FieldCondition(
        key=key,
        match=qdrant_models.MatchValue(value=value),
    )
