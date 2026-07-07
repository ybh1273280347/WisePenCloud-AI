from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from chat.application.tools.common.web_content_cache.core.models import (
    WebContentCacheMode,
    WebContentCacheValue,
)
from chat.core.persistence.redis._utils import to_jsonable
from chat.core.persistence.redis.base import RedisRepository

_VALUE_KEY_PREFIX = "wisepen:web_content_cache:value:"


class RedisWebContentCacheRepository(RedisRepository):
    """Redis 侧：URL 内容缓存读写。"""

    def __init__(self, *, redis_url: str) -> None:
        super().__init__(redis_url=redis_url)

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

        payload: dict[str, Any] = json.loads(raw)
        return WebContentCacheValue(
            user_id=str(payload["user_id"]),
            canonical_url=str(payload["canonical_url"]),
            final_url=_optional_str(payload.get("final_url")),
            cache_mode=WebContentCacheMode(str(payload["cache_mode"])),
            status_code=_optional_int(payload.get("status_code")),
            content_type=_optional_str(payload.get("content_type")),
            raw_html=_optional_str(payload.get("raw_html")),
            markdown=_optional_str(payload.get("markdown")),
            content_hash=_optional_str(payload.get("content_hash")),
            fetched_at=_optional_datetime(payload.get("fetched_at")),
            expire_at=_optional_datetime(payload.get("expire_at")),
            etag=_optional_str(payload.get("etag")),
            last_modified=_optional_str(payload.get("last_modified")),
            metadata=_metadata(payload.get("metadata")),
        )

    async def set_value(self, value: WebContentCacheValue) -> None:
        canonical_url = value.canonical_url.strip()
        payload = json.dumps(
            to_jsonable(
                {
                    **asdict(value),
                    "canonical_url": canonical_url,
                }
            ),
            ensure_ascii=False,
        )
        await self._redis.set(
            self._value_key(
                user_id=value.user_id,
                url=canonical_url,
                cache_mode=value.cache_mode,
            ),
            payload,
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


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def _optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(str(value))


def _metadata(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return value
    return {}


def _redis_ttl_seconds(expire_at: datetime | None) -> int:
    if expire_at is None:
        return 1

    expires_at = expire_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    return max(1, int((expires_at - now).total_seconds()))
