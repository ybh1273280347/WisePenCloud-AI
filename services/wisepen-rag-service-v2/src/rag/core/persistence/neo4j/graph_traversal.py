"""Neo4j 当前已发布图的有界路径查询 adapter。"""

from neo4j import AsyncDriver, RoutingControl

from rag.application.rag.acl import PermissionAuthorizer
from rag.domain.models.graph import (
    GraphStatus,
    KnowledgeEntityType,
    KnowledgeNode,
    KnowledgeNodeKind,
    KnowledgeRelationType,
)
from rag.domain.models.graph import (
    GraphTraversalRequest,
    TraversalDirection,
    TraversedEdge,
    TraversedPath,
)
from rag.domain.repositories.neo4j.graph_traversal import GraphTraversal
from .acl_predicate import acl_predicate

_PATH_PATTERNS = {
    (TraversalDirection.OUT, 1): "(seed)-[:RAG_V2_KNOWLEDGE_RELATION|RAG_V2_MENTION*1]->(target)",
    (TraversalDirection.OUT, 2): "(seed)-[:RAG_V2_KNOWLEDGE_RELATION|RAG_V2_MENTION*1..2]->(target)",
    (TraversalDirection.IN, 1): "(seed)<-[:RAG_V2_KNOWLEDGE_RELATION|RAG_V2_MENTION*1]-(target)",
    (TraversalDirection.IN, 2): "(seed)<-[:RAG_V2_KNOWLEDGE_RELATION|RAG_V2_MENTION*1..2]-(target)",
    (TraversalDirection.BOTH, 1): "(seed)-[:RAG_V2_KNOWLEDGE_RELATION|RAG_V2_MENTION*1]-(target)",
    (TraversalDirection.BOTH, 2): "(seed)-[:RAG_V2_KNOWLEDGE_RELATION|RAG_V2_MENTION*1..2]-(target)",
}


class Neo4jGraphTraversal(GraphTraversal):
    """查询无环路径，并对每条 evidence 资源执行统一 ACL 复查。"""

    def __init__(
        self,
        *,
        driver: AsyncDriver,
        database: str,
        authorizer: PermissionAuthorizer,
    ) -> None:
        self._driver = driver
        self._database = database
        self._authorizer = authorizer

    async def find_paths(
        self,
        request: GraphTraversalRequest,
    ) -> list[TraversedPath]:
        if not request.seed_node_ids or request.limit <= 0:
            return []
        pattern = _PATH_PATTERNS.get((request.direction, request.max_depth))
        if pattern is None:
            raise ValueError("graph traversal depth must be 1 or 2")

        evidence_acl, acl_parameters = acl_predicate(
            request.permission_scope,
            resource_alias="evidence",
        )
        path_node_acl, _ = acl_predicate(
            request.permission_scope,
            resource_alias="path_node",
        )

        result = await self._driver.execute_query(
            f"""
            MATCH (seed:RagV2Node)
            WHERE seed.node_id IN $seed_node_ids
            MATCH path={pattern}
            WHERE target <> seed
              AND all(path_node IN nodes(path)
                WHERE single(other IN nodes(path) WHERE other = path_node))
              AND all(path_node IN nodes(path)
                WHERE NOT path_node:RagV2ResourceNode OR {path_node_acl})
              AND all(relation IN relationships(path)
                WHERE (size($relation_types) = 0
                       OR coalesce(relation.relation_type, 'MENTIONS')
                          IN $relation_types)
                  AND EXISTS {{
                    MATCH (evidence:RagV2ResourceNode {{
                      resource_id: relation.evidence_resource_id
                    }})
                    WHERE evidence.graph_status = '{GraphStatus.PUBLISHED.value}'
                      AND evidence.content_revision = relation.source_content_revision
                      AND evidence.graph_revision = relation.graph_revision
                      AND {evidence_acl}
                  }})
            RETURN [path_node IN nodes(path) | {{
                     node_id: path_node.node_id,
                     kind: CASE
                       WHEN path_node:RagV2EntityNode THEN 'Entity'
                       WHEN path_node:RagV2ExternalSourceNode THEN 'ExternalSource'
                       ELSE 'Resource'
                     END,
                     label: coalesce(path_node.label, path_node.resource_id),
                     entity_type: path_node.entity_type,
                     resource_id: path_node.resource_id
                   }}] AS nodes,
                   [relation IN relationships(path) | {{
                     edge_id: coalesce(relation.edge_id, relation.mention_id),
                     source_node_id: startNode(relation).node_id,
                     target_node_id: endNode(relation).node_id,
                     relation_type: coalesce(relation.relation_type, 'MENTIONS'),
                     predicate: relation.predicate,
                     evidence_resource_id: relation.evidence_resource_id,
                     source_content_revision: relation.source_content_revision,
                     evidence_quotes: coalesce(
                       relation.evidence_quotes,
                       [relation.evidence_quote]
                     ),
                     evidence_source_ref_ids: coalesce(
                       relation.evidence_source_ref_ids,
                       relation.source_ref_ids
                     )
                   }}] AS edges
            ORDER BY size(edges), nodes[-1].node_id
            LIMIT $limit
            """,
            seed_node_ids=list(dict.fromkeys(request.seed_node_ids)),
            relation_types=[item.value for item in request.relation_types],
            limit=request.limit,
            **acl_parameters,
            database_=self._database,
            routing_=RoutingControl.READ,
        )
        paths = [_to_path(record) for record in result.records]
        readable_resource_ids = set(
            await self._authorizer.readable_resource_ids(
                (
                    resource_id
                    for path in paths
                    for resource_id in _path_resource_ids(path)
                ),
                scope=request.permission_scope,
            )
        )
        return [
            path
            for path in paths
            if _path_resource_ids(path).issubset(readable_resource_ids)
        ]


def _to_path(record) -> TraversedPath:
    return TraversedPath(
        nodes=[_to_node(item) for item in record["nodes"]],
        edges=[_to_edge(item) for item in record["edges"]],
    )


def _to_node(item: dict) -> KnowledgeNode:
    kind = KnowledgeNodeKind(item["kind"])
    return KnowledgeNode(
        node_id=item["node_id"],
        kind=kind,
        label=item["label"],
        entity_type=(
            KnowledgeEntityType(item["entity_type"])
            if kind is KnowledgeNodeKind.ENTITY
            else None
        ),
        resource_id=(
            item["resource_id"] if kind is KnowledgeNodeKind.RESOURCE else None
        ),
    )


def _to_edge(item: dict) -> TraversedEdge:
    return TraversedEdge(
        edge_id=item["edge_id"],
        source_node_id=item["source_node_id"],
        target_node_id=item["target_node_id"],
        relation_type=KnowledgeRelationType(item["relation_type"]),
        predicate=item.get("predicate"),
        evidence_resource_id=item["evidence_resource_id"],
        source_content_revision=item["source_content_revision"],
        evidence_quotes=list(item["evidence_quotes"]),
        evidence_source_ref_ids=list(item["evidence_source_ref_ids"]),
    )


def _path_resource_ids(path: TraversedPath) -> set[str]:
    return {
        *(edge.evidence_resource_id for edge in path.edges),
        *(
            node.resource_id
            for node in path.nodes
            if node.resource_id is not None
        ),
    }
