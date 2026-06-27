from __future__ import annotations

from typing import Protocol

from .models import (
    WebContentCacheEntry,
    WebContentCacheMode,
    WebContentCacheValue,
)


class WebContentCacheEntryRepository(Protocol):
    """Redis 侧：缓存索引读写与刷新锁。"""

    async def get_entry(
        self,
        *,
        user_id: str,
        url: str,
        cache_mode: WebContentCacheMode | str,
    ) -> WebContentCacheEntry | None:
        ...

    async def get_readable_entry(
        self,
        *,
        user_id: str,
        url: str,
    ) -> WebContentCacheEntry | None:
        ...

    async def set_entry(self, entry: WebContentCacheEntry) -> None:
        ...

    async def delete_entry(
        self,
        *,
        user_id: str,
        url: str,
        cache_mode: WebContentCacheMode | str,
    ) -> None:
        ...

    async def try_acquire_refresh_lock(
        self,
        *,
        key: str,
        ttl_seconds: int,
    ) -> bool:
        ...


class WebContentCacheValueRepository(Protocol):
    """MongoDB 侧：正文内容存储。"""

    async def get_value(self, *, doc_id: str) -> WebContentCacheValue | None:
        ...

    async def save_value(self, value: WebContentCacheValue) -> str:
        ...
