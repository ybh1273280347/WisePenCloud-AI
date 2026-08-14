"""知识图谱发布、反查和遍历的统一仓储契约。"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from rag.domain.models.acl import PermissionScope
from rag.domain.models.graph import (
    KnowledgeGraph,
    KnowledgeNode,
    KnowledgeRelationType,
    TraversalDirection,
)
from rag.domain.models.provenance import SourceEvidence


class KnowledgeGraphRevisionSupersededError(RuntimeError):
    """写入任务对应的内容版本已被更新版本取代。"""


@dataclass(slots=True)
class TraversedEdge:
    """图查询返回的边，并保留 EXPAND 回源所需的证据身份。"""

    edge_id: str
    source_node_id: str
    target_node_id: str
    relation_type: KnowledgeRelationType
    evidence_resource_id: str
    source_content_revision: str
    evidence_quotes: list[str]
    evidence_source_ref_ids: list[str]
    predicate: str | None = None


@dataclass(slots=True)
class TraversedPath:
    """Neo4j 有界遍历返回的节点和边序列。"""

    nodes: list[KnowledgeNode] = field(default_factory=list)
    edges: list[TraversedEdge] = field(default_factory=list)


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
        *,
        seed_node_ids: Sequence[str],
        permission_scope: PermissionScope,
        relation_types: Sequence[KnowledgeRelationType] = (),
        direction: TraversalDirection = TraversalDirection.BOTH,
        max_depth: int = 1,
        limit: int = 40,
    ) -> list[TraversedPath]: ...
