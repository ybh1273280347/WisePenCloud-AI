"""知识图谱发布、反查和遍历的统一仓储契约。"""

from collections.abc import Sequence
from typing import Protocol

from rag.domain.models.acl import PermissionScope
from rag.domain.models.graph import (
    GraphTraversalRequest,
    KnowledgeGraph,
    KnowledgeNode,
    TraversedPath,
)
from rag.domain.models.provenance import SourceEvidence


class KnowledgeGraphRevisionSupersededError(RuntimeError):
    """写入任务对应的内容版本已被更新版本取代。"""


class KnowledgeGraphRepository(Protocol):
    """管理知识图谱发布生命周期并查询当前已发布图。"""

    async def initialize(self) -> None: ...

    async def begin_build(
        self,
        *,
        resource_id: str,
        content_revision: str,
        document_version: int,
    ) -> None: ...

    async def publish(
        self,
        *,
        graph: KnowledgeGraph,
        document_version: int,
    ) -> None: ...

    async def skip(
        self,
        *,
        resource_id: str,
        content_revision: str,
        document_version: int,
    ) -> None: ...

    async def delete_resources(self, resource_ids: Sequence[str]) -> None: ...

    async def find_nodes(
        self,
        *,
        evidence: Sequence[SourceEvidence],
        permission_scope: PermissionScope,
        limit: int,
    ) -> list[KnowledgeNode]: ...

    async def find_paths(
        self,
        request: GraphTraversalRequest,
    ) -> list[TraversedPath]: ...
