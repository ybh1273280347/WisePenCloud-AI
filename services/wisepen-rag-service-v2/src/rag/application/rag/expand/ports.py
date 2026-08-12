"""EXPAND 能力依赖的外部查询 port。"""

from typing import Protocol

from .graph_traversal import GraphTraversalRequest, TraversedPath


class GraphTraversal(Protocol):
    """查询当前 published graph 中满足边界和权限的候选路径。"""

    async def find_paths(
        self,
        request: GraphTraversalRequest,
    ) -> list[TraversedPath]: ...
