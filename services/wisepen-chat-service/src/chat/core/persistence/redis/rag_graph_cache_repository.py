from __future__ import annotations

from hashlib import sha256

import msgspec
from redis.asyncio import Redis

from chat.application.rag.cache.graph_enhancement import RagGraphEnhancementCacheKey
from chat.application.rag.graph import (
    RagGraphEnhancementResult,
)
from chat.core.persistence.redis._utils.cache_codec import dumps_cache, loads_cache
from chat.core.persistence.redis.base import RedisRepository

_KEY_PREFIX = "wisepen:rag:graph_enhancement:"


class RedisRagGraphEnhancementCache(RedisRepository):
    """Redis 侧 Neo4j graph enhancement 结果缓存。"""

    __slots__ = ("_ttl_seconds",)

    def __init__(self, *, redis_client: Redis, ttl_seconds: int) -> None:
        super().__init__(redis_client=redis_client)
        self._ttl_seconds = ttl_seconds

    async def get_graph_enhancement(
            self,
            key: RagGraphEnhancementCacheKey,
    ) -> RagGraphEnhancementResult | None:
        if self._ttl_seconds <= 0:
            return None

        raw = await self._redis.get(self._key(key))
        if raw is None:
            return None
        try:
            return loads_cache(raw, RagGraphEnhancementResult)
        except (msgspec.DecodeError, msgspec.ValidationError):
            return None

    async def set_graph_enhancement(
            self,
            key: RagGraphEnhancementCacheKey,
            result: RagGraphEnhancementResult,
    ) -> None:
        if self._ttl_seconds <= 0:
            return

        await self._redis.set(
            self._key(key),
            dumps_cache(result),
            ex=self._ttl_seconds,
        )

    @classmethod
    def _key(cls, key: RagGraphEnhancementCacheKey) -> str:
        return f"{_KEY_PREFIX}{sha256(dumps_cache(key)).hexdigest()}"
