"""跨仓储、应用和 API 使用的知识图谱遍历契约。"""

from dataclasses import dataclass, field
from enum import StrEnum

from rag.domain.acl import PermissionScope
from rag.domain.knowledge_graph import KnowledgeNode, KnowledgeRelationType


class TraversalDirection(StrEnum):
    IN = "in"
    OUT = "out"
    BOTH = "both"


@dataclass(slots=True)
class TraversedEdge:
    """图遍历返回的边视图，保留回源证据引用供 EXPAND 继续核验。"""

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
    """一次有界图遍历得到的节点路径。"""

    nodes: list[KnowledgeNode] = field(default_factory=list)
    edges: list[TraversedEdge] = field(default_factory=list)


@dataclass(slots=True)
class GraphTraversalRequest:
    """提交给图遍历仓储 port 的查询约束。"""

    seed_node_ids: list[str]
    permission_scope: PermissionScope
    relation_types: list[KnowledgeRelationType] = field(default_factory=list)
    direction: TraversalDirection = TraversalDirection.BOTH
    max_depth: int = 1
    limit: int = 40
