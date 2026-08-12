"""知识图谱遍历仓储契约。"""

from typing import Protocol

from rag.domain.models.graph import GraphTraversalRequest, TraversedPath


class GraphTraversal(Protocol):
    """查询当前 published graph 中满足边界和权限的候选路径。"""

    async def find_paths(
        self,
        request: GraphTraversalRequest,
    ) -> list[TraversedPath]: ...
