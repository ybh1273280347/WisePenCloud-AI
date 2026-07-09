from __future__ import annotations

from hashlib import sha256

from redis.asyncio import Redis

from chat.application.rag.cache.evidence_materialization import (
    RagEvidenceMaterializationCacheScope,
    RagMaterializedEvidenceView,
)
from chat.core.persistence.redis._utils.cache_codec import dumps_cache, loads_cache_or_none
from chat.core.persistence.redis.base import RedisRepository

_KEY_PREFIX = "wisepen:rag:evidence_materialized:"


class RedisRagEvidenceMaterializationCache(RedisRepository):
    """Redis 短 TTL evidence 物化缓存。"""

    __slots__ = ("_ttl_seconds",)

    def __init__(self, *, redis_client: Redis, ttl_seconds: int) -> None:
        super().__init__(redis_client=redis_client)
        self._ttl_seconds = ttl_seconds

    async def get_many(
            self,
            *,
            scope: RagEvidenceMaterializationCacheScope,
            child_chunk_ids: tuple[str, ...],
    ) -> dict[str, RagMaterializedEvidenceView]:
        if self._ttl_seconds <= 0 or not child_chunk_ids:
            return {}

        keys = [self._key(scope=scope, child_chunk_id=chunk_id) for chunk_id in child_chunk_ids]
        values = await self._redis.mget(keys)
        result: dict[str, RagMaterializedEvidenceView] = {}
        for chunk_id, raw in zip(child_chunk_ids, values, strict=True):
            if raw is None:
                continue
            view = loads_cache_or_none(raw, RagMaterializedEvidenceView)
            if view is not None:
                result[chunk_id] = view
        return result

    async def set_many(
            self,
            *,
            scope: RagEvidenceMaterializationCacheScope,
            views_by_child_id: dict[str, RagMaterializedEvidenceView],
    ) -> None:
        if self._ttl_seconds <= 0 or not views_by_child_id:
            return

        async with self._redis.pipeline(transaction=True) as pipe:
            for child_chunk_id, view in views_by_child_id.items():
                await pipe.set(
                    self._key(scope=scope, child_chunk_id=child_chunk_id),
                    dumps_cache(view),
                    ex=self._ttl_seconds,
                )
            await pipe.execute()

    @classmethod
    def _key(
            cls,
            *,
            scope: RagEvidenceMaterializationCacheScope,
            child_chunk_id: str,
    ) -> str:
        scope_hash = cls._hash(
            "\n".join(
                (
                    scope.user_id,
                    scope.session_id,
                    scope.resource_id,
                    scope.permission_scope_key,
                )
            )
        )
        return f"{_KEY_PREFIX}{scope_hash}:{cls._hash(child_chunk_id)}"

    @staticmethod
    def _hash(value: str) -> str:
        return sha256(value.encode("utf-8")).hexdigest()
