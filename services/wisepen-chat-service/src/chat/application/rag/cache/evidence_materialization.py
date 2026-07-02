from __future__ import annotations

from .models import AuthorizedEvidenceMaterializationCacheKey


class AuthorizedEvidenceMaterializationCache:
    """P1：查询期已授权 evidence 物化缓存占位。

    负责的位置：
    - direct / graph evidence id -> child evidence view
    - child evidence -> parent context view
    - citation / section path / short evidence text

    不负责 query cache、retrieval result cache 或 final answer cache。
    任何 user、session、ACL、corpus、document version 不确定时都应 cache miss。
    """

    __slots__ = ()

    async def get(self, key: AuthorizedEvidenceMaterializationCacheKey) -> None:
        """占位：后续接入 Redis 短 TTL 后返回已授权物化视图。"""
        return None

    async def put(
        self,
        key: AuthorizedEvidenceMaterializationCacheKey,
        value: object,
    ) -> None:
        """占位：后续接入 Redis 短 TTL 后写入已授权物化视图。"""
        return None
