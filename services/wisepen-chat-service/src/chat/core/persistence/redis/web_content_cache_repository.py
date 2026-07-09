from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256

import msgspec
from redis.asyncio import Redis

from chat.application.tools.common.web_content_cache.core.models import (
    WebContentCacheMode,
    WebContentCacheValue,
)
from chat.core.persistence.redis._utils.cache_codec import dumps_cache, loads_cache
from chat.core.persistence.redis.base import RedisRepository

_VALUE_KEY_PREFIX = "wisepen:web_content_cache:value:"


class RedisWebContentCacheRepository(RedisRepository):
    """Redis 侧：URL 内容缓存读写。"""

    def __init__(self, *, redis_client: Redis) -> None:
        super().__init__(redis_client=redis_client)

    async def get_value(
            self,
            *,
            user_id: str,
            url: str,
            cache_mode: WebContentCacheMode | str,
    ) -> WebContentCacheValue | None:
        mode = WebContentCacheMode(cache_mode)
        raw = await self._redis.get(self._value_key(user_id=user_id, url=url, cache_mode=mode))
        if raw is None:
            return None

        try:
            return loads_cache(raw, WebContentCacheValue)
        except (msgspec.DecodeError, msgspec.ValidationError):
            return None

    async def set_value(self, value: WebContentCacheValue) -> None:
        canonical_url = value.canonical_url.strip()
        stored = replace(value, canonical_url=canonical_url)
        await self._redis.set(
            self._value_key(
                user_id=value.user_id,
                url=canonical_url,
                cache_mode=value.cache_mode,
            ),
            dumps_cache(stored),
            ex=_redis_ttl_seconds(value.expire_at),
        )

    async def delete_value(
            self,
            *,
            user_id: str,
            url: str,
            cache_mode: WebContentCacheMode | str,
    ) -> None:
        mode = WebContentCacheMode(cache_mode)
        await self._redis.delete(self._value_key(user_id=user_id, url=url, cache_mode=mode))

    @classmethod
    def _value_key(cls, *, user_id: str, url: str, cache_mode: WebContentCacheMode) -> str:
        url_hash = cls._hash(url.strip())
        if cache_mode == WebContentCacheMode.PUBLIC:
            return f"{_VALUE_KEY_PREFIX}public:{url_hash}"
        return f"{_VALUE_KEY_PREFIX}private:{cls._hash(user_id)}:{url_hash}"

    @staticmethod
    def _hash(value: str) -> str:
        return sha256(value.encode("utf-8")).hexdigest()


def _redis_ttl_seconds(expire_at: datetime | None) -> int:
    if expire_at is None:
        return 1

    expires_at = expire_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    return max(1, int((expires_at - now).total_seconds()))
