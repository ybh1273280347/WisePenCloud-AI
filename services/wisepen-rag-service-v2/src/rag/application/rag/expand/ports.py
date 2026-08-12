"""EXPAND 有界图路径查询所需的 port 和路径事实。"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from rag.domain.acl import PermissionScope
from rag.domain.knowledge_graph import (
    KnowledgeNode,
    KnowledgeRelationType,
)


class TraversalDirection(StrEnum):
    IN = "in"
    OUT = "out"
    BOTH = "both"


@dataclass(slots=True)
class TraversedEdge:
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
    nodes: list[KnowledgeNode] = field(default_factory=list)
    edges: list[TraversedEdge] = field(default_factory=list)


@dataclass(slots=True)
class GraphTraversalRequest:
    seed_node_ids: list[str]
    permission_scope: PermissionScope
    relation_types: list[KnowledgeRelationType] = field(default_factory=list)
    direction: TraversalDirection = TraversalDirection.BOTH
    max_depth: int = 1
    limit: int = 40


class GraphTraversal(Protocol):
    """查询当前 published graph 中满足边界和权限的候选路径。"""

    async def find_paths(
        self,
        request: GraphTraversalRequest,
    ) -> list[TraversedPath]: ...
