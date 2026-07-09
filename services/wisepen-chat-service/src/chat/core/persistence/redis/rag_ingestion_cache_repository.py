from __future__ import annotations

from hashlib import sha256

from redis.asyncio import Redis

from chat.application.rag.cache.ingestion_deterministic import (
    RagChunkingCacheKey,
    RagContextIndexingCacheKey,
    RagEmbeddingCacheKey,
)
from chat.application.rag.ingestion.models import (
    RagChildChunk,
    RagChunkingResult,
)
from chat.core.persistence.redis._utils.cache_codec import dumps_cache, loads_cache_or_none
from chat.core.persistence.redis.base import RedisRepository

_CHUNKING_KEY_PREFIX = "wisepen:rag:ingestion:chunking:"
_CONTEXT_INDEXING_KEY_PREFIX = "wisepen:rag:ingestion:context_indexing:"
_EMBEDDING_KEY_PREFIX = "wisepen:rag:ingestion:embedding:"


class RedisRagIngestionDeterministicCache(RedisRepository):
    """Redis 侧 RAG 入库确定性中间结果缓存。"""

    __slots__ = ("_ttl_seconds",)

    def __init__(self, *, redis_client: Redis, ttl_seconds: int) -> None:
        super().__init__(redis_client=redis_client)
        self._ttl_seconds = ttl_seconds

    async def get_chunking_result(
        self,
        key: RagChunkingCacheKey,
    ) -> RagChunkingResult | None:
        raw = await self._get(self._chunking_key(key))
        if raw is None:
            return None
        return loads_cache_or_none(raw, RagChunkingResult)

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
        return loads_cache_or_none(raw, RagChildChunk)

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
        values = await self._redis.mget(
            [self._embedding_key(keys[chunk_id]) for chunk_id in chunk_ids]
        )
        result: dict[str, list[float]] = {}
        for chunk_id, raw in zip(chunk_ids, values, strict=True):
            if raw is None:
                continue
            vector = loads_cache_or_none(raw, list[float])
            if vector is not None:
                result[chunk_id] = vector
        return result

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
                    dumps_cache(vector),
                    ex=self._ttl_seconds,
                )
            await pipe.execute()

    async def _get(self, key: str) -> str | None:
        if self._ttl_seconds <= 0:
            return None
        return await self._redis.get(key)

    async def _set(self, key: str, payload: bytes) -> None:
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
    def _hash(value: bytes) -> str:
        return sha256(value).hexdigest()


def _encode(value: object) -> bytes:
    return dumps_cache(value)
