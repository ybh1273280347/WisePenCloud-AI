from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

import redis.asyncio as redis

from chat.application.tools.common.web_content_cache import (
    WebContentCacheEntry,
    WebContentCacheMode,
)

_ENTRY_KEY_PREFIX = "wisepen:web_content_cache:entry:"
_REFRESH_LOCK_KEY_PREFIX = "wisepen:web_content_cache:refresh_lock:"


class RedisWebContentCacheEntryRepository:
    """Redis 侧：URL 缓存索引读写与刷新锁。"""

    __slots__ = ("_redis",)

    def __init__(self, *, redis_url: str) -> None:
        self._redis = redis.from_url(redis_url, decode_responses=True)

    async def get_entry(
            self,
            *,
            user_id: str,
            url: str,
            cache_mode: WebContentCacheMode | str,
    ) -> WebContentCacheEntry | None:
        mode = WebContentCacheMode(cache_mode)
        raw = await self._redis.get(self._entry_key(user_id=user_id, url=url, cache_mode=mode))
        if raw is None:
            return None

        payload: dict[str, Any] = json.loads(raw)
        return WebContentCacheEntry(
            user_id=str(payload["user_id"]),
            url_hash=str(payload["url_hash"]),
            canonical_url=str(payload["canonical_url"]),
            mongo_doc_id=str(payload["mongo_doc_id"]),
            cache_mode=WebContentCacheMode(str(payload["cache_mode"])),
            soft_expire_at=datetime.fromisoformat(str(payload["soft_expire_at"])),
            hard_expire_at=datetime.fromisoformat(str(payload["hard_expire_at"])),
            etag=(
                str(payload["etag"])
                if payload.get("etag") is not None
                else None
            ),
            last_modified=(
                str(payload["last_modified"])
                if payload.get("last_modified") is not None
                else None
            ),
        )

    async def get_readable_entry(
            self,
            *,
            user_id: str,
            url: str,
    ) -> WebContentCacheEntry | None:
        private_entry = await self.get_entry(
            user_id=user_id,
            url=url,
            cache_mode=WebContentCacheMode.PRIVATE,
        )
        if private_entry is not None:
            return private_entry

        return await self.get_entry(
            user_id=user_id,
            url=url,
            cache_mode=WebContentCacheMode.PUBLIC,
        )

    async def set_entry(self, entry: WebContentCacheEntry) -> None:
        canonical_url = entry.canonical_url.strip()
        payload = json.dumps(
            _jsonable(
                {
                    **asdict(entry),
                    "url_hash": self.url_hash(canonical_url),
                    "canonical_url": canonical_url,
                }
            ),
            ensure_ascii=False,
        )
        ttl_seconds = _redis_ttl_seconds(entry.hard_expire_at)
        await self._redis.set(
            self._entry_key(
                user_id=entry.user_id,
                url=canonical_url,
                cache_mode=entry.cache_mode,
            ),
            payload,
            ex=ttl_seconds,
        )

    async def delete_entry(
            self,
            *,
            user_id: str,
            url: str,
            cache_mode: WebContentCacheMode | str,
    ) -> None:
        mode = WebContentCacheMode(cache_mode)
        await self._redis.delete(self._entry_key(user_id=user_id, url=url, cache_mode=mode))

    async def try_acquire_refresh_lock(
            self,
            *,
            key: str,
            ttl_seconds: int,
    ) -> bool:
        locked = await self._redis.set(
            f"{_REFRESH_LOCK_KEY_PREFIX}{self._hash(key)}",
            "1",
            ex=max(1, ttl_seconds),
            nx=True,
        )
        return bool(locked)

    @classmethod
    def _entry_key(cls, *, user_id: str, url: str, cache_mode: WebContentCacheMode) -> str:
        url_hash = cls.url_hash(url)
        if cache_mode == WebContentCacheMode.PUBLIC:
            return f"{_ENTRY_KEY_PREFIX}public:{url_hash}"
        return f"{_ENTRY_KEY_PREFIX}private:{cls._hash(user_id)}:{url_hash}"

    @classmethod
    def url_hash(cls, url: str) -> str:
        canonical_url = url.strip()
        return cls._hash(canonical_url)

    @staticmethod
    def _hash(value: str) -> str:
        return sha256(value.encode("utf-8")).hexdigest()


def _redis_ttl_seconds(hard_expire_at: datetime) -> int:
    expires_at = hard_expire_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    return max(1, int((expires_at - now).total_seconds()))


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}

    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, WebContentCacheMode):
        return value.value

    try:
        json.dumps(value)
    except TypeError:
        return str(value)

    return value
