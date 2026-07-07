from __future__ import annotations

from typing import Protocol

from .models import (
    WebContentCacheMode,
    WebContentCacheValue,
)


class WebContentCacheRepository(Protocol):
    """Redis 侧：URL 内容缓存读写。"""

    async def get_value(
            self,
            *,
            user_id: str,
            url: str,
            cache_mode: WebContentCacheMode | str,
    ) -> WebContentCacheValue | None:
        ...

    async def set_value(self, value: WebContentCacheValue) -> None:
        ...

    async def delete_value(
            self,
            *,
            user_id: str,
            url: str,
            cache_mode: WebContentCacheMode | str,
    ) -> None:
        ...
