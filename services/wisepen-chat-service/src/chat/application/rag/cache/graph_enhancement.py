from __future__ import annotations

from .models import GraphEnhancementCacheKey


class GraphEnhancementCache:
    """P2：Neo4j 图增强缓存占位。

    负责的位置：
    - concept path expansion
    - relation evidence ids
    - ontology hints
    - graph evidence organization

    缓存结果进入 Context Builder 前，仍必须经过 evidence 权限校验和物化。
    """

    __slots__ = ()

    async def get(self, key: GraphEnhancementCacheKey) -> None:
        """占位：后续图增强链路稳定后返回 graph evidence ids / ontology hints。"""
        return None

    async def put(self, key: GraphEnhancementCacheKey, value: object) -> None:
        """占位：后续图增强链路稳定后写入 graph enhancement 结果。"""
        return None
