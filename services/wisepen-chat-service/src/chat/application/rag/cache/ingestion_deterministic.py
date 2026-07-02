from __future__ import annotations

from .models import IngestionDeterministicCacheKey


class IngestionDeterministicCache:
    """P0：入库阶段确定性派生产物缓存占位。

    负责的位置：
    - markdown chunking result
    - context indexing result
    - embedding result
    - graph extraction result

    不负责 ACL projection；权限投影必须由入库链路按最新权限事实重建。
    """

    __slots__ = ()

    async def get(self, key: IngestionDeterministicCacheKey) -> None:
        """占位：后续接入持久化后返回命中的派生产物。"""
        return None

    async def put(self, key: IngestionDeterministicCacheKey, value: object) -> None:
        """占位：后续接入持久化后写入派生产物。"""
        return None
