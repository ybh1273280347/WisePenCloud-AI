from __future__ import annotations

import json
from dataclasses import asdict
from hashlib import sha256
from typing import Any

from chat.application.rag.cache.ingestion_deterministic import (
    RagChunkingCacheKey,
    RagContextIndexingCacheKey,
    RagEmbeddingCacheKey,
)
from chat.application.rag.ingestion.models import (
    RagChildChunk,
    RagChunkExtraIndex,
    RagChunkingResult,
    RagParentChunk,
)
from chat.application.rag.utils import read_optional_text, read_text_tuple
from chat.application.utils.chunking_engine.models import IndexKind
from chat.core.persistence.redis._utils import to_jsonable
from chat.core.persistence.redis.base import RedisRepository

_CHUNKING_KEY_PREFIX = "wisepen:rag:ingestion:chunking:"
_CONTEXT_INDEXING_KEY_PREFIX = "wisepen:rag:ingestion:context_indexing:"
_EMBEDDING_KEY_PREFIX = "wisepen:rag:ingestion:embedding:"


class RedisRagIngestionDeterministicCache(RedisRepository):
    """Redis 侧 RAG 入库确定性中间结果缓存。"""

    __slots__ = ("_ttl_seconds",)

    def __init__(self, *, redis_url: str, ttl_seconds: int) -> None:
        super().__init__(redis_url=redis_url)
        self._ttl_seconds = ttl_seconds

    async def get_chunking_result(
            self,
            key: RagChunkingCacheKey,
    ) -> RagChunkingResult | None:
        raw = await self._get(self._chunking_key(key))
        if raw is None:
            return None
        return _decode_chunking_result(json.loads(raw))

    async def set_chunking_result(
            self,
            key: RagChunkingCacheKey,
            result: RagChunkingResult,
    ) -> None:
        await self._set(self._chunking_key(key), _encode(result))

    async def get_context_indexed_child(
            self,
            key: RagContextIndexingCacheKey,
    ) -> RagChildChunk | None:
        raw = await self._get(self._context_indexing_key(key))
        if raw is None:
            return None
        return _decode_child_chunk(json.loads(raw))

    async def set_context_indexed_child(
            self,
            key: RagContextIndexingCacheKey,
            child: RagChildChunk,
    ) -> None:
        await self._set(self._context_indexing_key(key), _encode(child))

    async def get_embedding_vectors(
            self,
            keys: dict[str, RagEmbeddingCacheKey],
    ) -> dict[str, list[float]]:
        if not keys:
            return {}

        chunk_ids = tuple(keys)
        values = await self._redis.mget([
            self._embedding_key(keys[chunk_id])
            for chunk_id in chunk_ids
        ])
        return {
            chunk_id: [float(item) for item in json.loads(raw)]
            for chunk_id, raw in zip(chunk_ids, values, strict=True)
            if raw is not None
        }

    async def set_embedding_vectors(
            self,
            vectors: dict[str, tuple[RagEmbeddingCacheKey, list[float]]],
    ) -> None:
        if self._ttl_seconds <= 0 or not vectors:
            return

        async with self._redis.pipeline(transaction=True) as pipe:
            for key, vector in vectors.values():
                await pipe.set(
                    self._embedding_key(key),
                    json.dumps(vector, ensure_ascii=False),
                    ex=self._ttl_seconds,
                )
            await pipe.execute()

    async def _get(self, key: str) -> str | None:
        if self._ttl_seconds <= 0:
            return None
        return await self._redis.get(key)

    async def _set(self, key: str, payload: str) -> None:
        if self._ttl_seconds <= 0:
            return
        await self._redis.set(key, payload, ex=self._ttl_seconds)

    @classmethod
    def _chunking_key(cls, key: RagChunkingCacheKey) -> str:
        return f"{_CHUNKING_KEY_PREFIX}{cls._hash(_encode(key))}"

    @classmethod
    def _context_indexing_key(cls, key: RagContextIndexingCacheKey) -> str:
        return f"{_CONTEXT_INDEXING_KEY_PREFIX}{cls._hash(_encode(key))}"

    @classmethod
    def _embedding_key(cls, key: RagEmbeddingCacheKey) -> str:
        return f"{_EMBEDDING_KEY_PREFIX}{cls._hash(_encode(key))}"

    @staticmethod
    def _hash(value: str) -> str:
        return sha256(value.encode("utf-8")).hexdigest()


def _encode(value: object) -> str:
    return json.dumps(to_jsonable(asdict(value)), ensure_ascii=False, sort_keys=True)


def _decode_chunking_result(payload: dict[str, Any]) -> RagChunkingResult:
    return RagChunkingResult(
        parent_chunks=tuple(_decode_parent_chunk(item) for item in payload.get("parent_chunks", [])),
        child_chunks=tuple(_decode_child_chunk(item) for item in payload.get("child_chunks", [])),
        pipeline=str(payload["pipeline"]),
        resource_id=str(payload.get("resource_id") or ""),
        document_version=str(payload.get("document_version") or ""),
    )


def _decode_parent_chunk(payload: dict[str, Any]) -> RagParentChunk:
    return RagParentChunk(
        chunk_id=str(payload["chunk_id"]),
        text=str(payload["text"]),
        chunk_index=int(payload["chunk_index"]),
        start_offset=_optional_int(payload.get("start_offset")),
        end_offset=_optional_int(payload.get("end_offset")),
        extra_indexes=_decode_extra_indexes(payload.get("extra_indexes")),
        content_hash=str(payload.get("content_hash") or ""),
    )


def _decode_child_chunk(payload: dict[str, Any]) -> RagChildChunk:
    return RagChildChunk(
        chunk_id=str(payload["chunk_id"]),
        text=str(payload["text"]),
        chunk_index=int(payload["chunk_index"]),
        parent_chunk_id=str(payload["parent_chunk_id"]),
        start_offset=_optional_int(payload.get("start_offset")),
        end_offset=_optional_int(payload.get("end_offset")),
        extra_indexes=_decode_extra_indexes(payload.get("extra_indexes")),
        content_hash=str(payload.get("content_hash") or ""),
        indexing_context=str(payload.get("indexing_context") or ""),
        indexing_text=str(payload.get("indexing_text") or ""),
    )


def _decode_extra_indexes(value: object) -> tuple[RagChunkExtraIndex, ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(
        RagChunkExtraIndex(
            index_name=str(item["index_name"]),
            index_kind=IndexKind(str(item["index_kind"])),
            start_offset=_optional_int(item.get("start_offset")),
            end_offset=_optional_int(item.get("end_offset")),
            section_path=read_text_tuple(item.get("section_path")),
            page_label=read_optional_text(item.get("page_label")),
            anchor_label=read_optional_text(item.get("anchor_label")),
        )
        for item in value
        if isinstance(item, dict)
    )


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)

