"""Neo4j v2 知识图谱发布与查询的统一 adapter。"""

from collections.abc import Sequence

from neo4j import AsyncDriver, RoutingControl

from rag.application.rag.index.constructor.graph_merge import resource_node_id
from rag.domain.models.acl import PermissionScope
from rag.domain.models.graph import (
    GraphStatus,
    GraphTraversalRequest,
    KnowledgeEntityType,
    KnowledgeGraph,
    KnowledgeNode,
    KnowledgeNodeKind,
    KnowledgeRelationType,
    TraversalDirection,
    TraversedEdge,
    TraversedPath,
)
from rag.domain.models.provenance import SourceEvidence
from rag.domain.repositories.neo4j.knowledge_graph_repository import (
    KnowledgeGraphRepository,
    KnowledgeGraphRevisionSupersededError,
)

_NODE_LABEL = "RagV2Node"
_RESOURCE_LABEL = "RagV2ResourceNode"
_ENTITY_LABEL = "RagV2EntityNode"
_EXTERNAL_SOURCE_LABEL = "RagV2ExternalSourceNode"
_RELATION_TYPE = "RAG_V2_KNOWLEDGE_RELATION"
_MENTION_TYPE = "RAG_V2_MENTION"

_SCHEMA_QUERIES = (
    """
    CREATE CONSTRAINT rag_v2_node_id IF NOT EXISTS
    FOR (node:RagV2Node) REQUIRE node.node_id IS UNIQUE
    """,
    """
    CREATE INDEX rag_v2_relation_resource IF NOT EXISTS
    FOR ()-[relation:RAG_V2_KNOWLEDGE_RELATION]-()
    ON (relation.evidence_resource_id)
    """,
    """
    CREATE INDEX rag_v2_mention_resource IF NOT EXISTS
    FOR ()-[mention:RAG_V2_MENTION]-()
    ON (mention.evidence_resource_id)
    """,
)

_BEGIN_BUILD = f"""
MERGE (resource:{_NODE_LABEL}:{_RESOURCE_LABEL} {{node_id: $node_id}})
ON CREATE SET resource.document_version = $document_version
WITH resource
WHERE resource.document_version IS NULL
   OR resource.document_version <= $document_version
SET resource.resource_id = $resource_id,
    resource.content_revision = $content_revision,
    resource.document_version = $document_version,
    resource.graph_status = '{GraphStatus.BUILDING.value}',
    resource.graph_revision = null
RETURN resource.resource_id AS resource_id
"""

_UPSERT_ENTITIES = f"""
UNWIND $nodes AS item
MERGE (node:{_NODE_LABEL}:{_ENTITY_LABEL} {{node_id: item.node_id}})
SET node.label = item.label,
    node.entity_type = item.entity_type
"""

_UPSERT_EXTERNAL_SOURCES = f"""
UNWIND $nodes AS item
MERGE (node:{_NODE_LABEL}:{_EXTERNAL_SOURCE_LABEL} {{node_id: item.node_id}})
SET node.label = item.label
"""

_UPSERT_RELATIONS = f"""
UNWIND $relations AS item
MATCH (source:{_NODE_LABEL} {{node_id: item.source_node_id}})
MATCH (target:{_NODE_LABEL} {{node_id: item.target_node_id}})
MERGE (source)-[relation:{_RELATION_TYPE} {{edge_id: item.edge_id}}]->(target)
SET relation.relation_type = item.relation_type,
    relation.predicate = item.predicate,
    relation.evidence_resource_id = $resource_id,
    relation.evidence_quotes = item.evidence_quotes,
    relation.evidence_source_ref_ids = item.evidence_source_ref_ids,
    relation.source_content_revision = $content_revision,
    relation.graph_revision = $graph_revision
"""

_UPSERT_MENTIONS = f"""
UNWIND $mentions AS item
MATCH (resource:{_RESOURCE_LABEL} {{resource_id: $resource_id}})
MATCH (target:{_NODE_LABEL} {{node_id: item.node_id}})
MERGE (resource)-[mention:{_MENTION_TYPE} {{mention_id: item.mention_id}}]->(target)
SET mention.reading_block_id = item.reading_block_id,
    mention.source_ref_ids = item.source_ref_ids,
    mention.evidence_quote = item.evidence_quote,
    mention.evidence_resource_id = $resource_id,
    mention.source_content_revision = $content_revision,
    mention.graph_revision = $graph_revision
"""

_PUBLISH = f"""
MATCH (resource:{_RESOURCE_LABEL} {{resource_id: $resource_id}})
WHERE resource.document_version = $document_version
  AND resource.content_revision = $content_revision
  AND resource.graph_status = '{GraphStatus.BUILDING.value}'
SET resource.graph_status = '{GraphStatus.PUBLISHED.value}',
    resource.graph_revision = $graph_revision
RETURN resource.resource_id AS resource_id
"""

_SKIP = f"""
MATCH (resource:{_RESOURCE_LABEL} {{resource_id: $resource_id}})
WHERE resource.document_version = $document_version
  AND resource.content_revision = $content_revision
SET resource.graph_status = '{GraphStatus.SKIPPED.value}',
    resource.graph_revision = null
RETURN resource.resource_id AS resource_id
"""

_DELETE_OLD_RELATIONS = f"""
MATCH ()-[relation:{_RELATION_TYPE}]->()
WHERE relation.evidence_resource_id = $resource_id
  AND relation.graph_revision <> $graph_revision
DELETE relation
"""

_DELETE_OLD_MENTIONS = f"""
MATCH (resource:{_RESOURCE_LABEL} {{resource_id: $resource_id}})-[mention:{_MENTION_TYPE}]->()
WHERE mention.graph_revision <> $graph_revision
DELETE mention
"""

_DELETE_RESOURCES = f"""
MATCH ()-[relation:{_RELATION_TYPE}]->()
WHERE relation.evidence_resource_id IN $resource_ids
DELETE relation
WITH 1 AS ignored
MATCH (resource:{_RESOURCE_LABEL})
WHERE resource.resource_id IN $resource_ids
DETACH DELETE resource
"""

_DELETE_ORPHAN_NODES = f"""
MATCH (node:{_NODE_LABEL})
WHERE NOT node:{_RESOURCE_LABEL} AND NOT (node)--()
DELETE node
"""

_DELETE_ORPHAN_GROUP_ACLS = """
MATCH (acl:RagV2ResourceGroupAcl)
WHERE NOT ()-[:RAG_V2_HAS_GROUP_ACL]->(acl)
DELETE acl
"""

_FIND_NODES = """
UNWIND $evidence AS item
MATCH (resource:RagV2ResourceNode {{resource_id: item.resource_id}})
      -[mention:RAG_V2_MENTION]->(node:RagV2Node)
WHERE resource.graph_status = $published_status
  AND resource.content_revision = item.content_revision
  AND mention.source_content_revision = item.content_revision
  AND mention.graph_revision = resource.graph_revision
  AND item.source_ref_id IN mention.source_ref_ids
  AND {acl_filter}
RETURN DISTINCT node.node_id AS node_id,
       CASE
           WHEN node:RagV2EntityNode THEN 'Entity'
           WHEN node:RagV2ExternalSourceNode THEN 'ExternalSource'
           ELSE 'Resource'
       END AS kind,
       coalesce(node.label, node.resource_id) AS label,
       node.entity_type AS entity_type,
       node.resource_id AS resource_id
ORDER BY node_id
LIMIT $limit
"""

_PATH_PATTERNS = {
    (
        TraversalDirection.OUT,
        1,
    ): "(seed)-[:RAG_V2_KNOWLEDGE_RELATION|RAG_V2_MENTION*1]->(target)",
    (
        TraversalDirection.OUT,
        2,
    ): "(seed)-[:RAG_V2_KNOWLEDGE_RELATION|RAG_V2_MENTION*1..2]->(target)",
    (
        TraversalDirection.IN,
        1,
    ): "(seed)<-[:RAG_V2_KNOWLEDGE_RELATION|RAG_V2_MENTION*1]-(target)",
    (
        TraversalDirection.IN,
        2,
    ): "(seed)<-[:RAG_V2_KNOWLEDGE_RELATION|RAG_V2_MENTION*1..2]-(target)",
    (
        TraversalDirection.BOTH,
        1,
    ): "(seed)-[:RAG_V2_KNOWLEDGE_RELATION|RAG_V2_MENTION*1]-(target)",
    (
        TraversalDirection.BOTH,
        2,
    ): "(seed)-[:RAG_V2_KNOWLEDGE_RELATION|RAG_V2_MENTION*1..2]-(target)",
}


class Neo4jKnowledgeGraphRepository(KnowledgeGraphRepository):
    """管理 v2 Neo4j 知识图谱的发布生命周期和查询。"""

    def __init__(self, *, driver: AsyncDriver, database: str) -> None:
        if not database.strip():
            raise ValueError("database must not be empty")
        self._driver = driver
        self._database = database

    async def initialize(self) -> None:
        for query in _SCHEMA_QUERIES:
            await self._driver.execute_query(query, database_=self._database)

    async def begin_build(
        self,
        *,
        resource_id: str,
        content_revision: str,
        document_version: int,
    ) -> None:
        result = await self._driver.execute_query(
            _BEGIN_BUILD,
            node_id=resource_node_id(resource_id),
            resource_id=resource_id,
            content_revision=content_revision,
            document_version=document_version,
            database_=self._database,
        )
        if not result.records:
            raise KnowledgeGraphRevisionSupersededError(
                f"content revision {content_revision} was superseded"
            )

    async def publish(
        self,
        *,
        graph: KnowledgeGraph,
        document_version: int,
    ) -> None:
        common = {
            "resource_id": graph.resource_id,
            "content_revision": graph.content_revision,
            "graph_revision": graph.graph_revision,
            "document_version": document_version,
            "database_": self._database,
        }
        await self._driver.execute_query(
            _UPSERT_ENTITIES,
            nodes=[
                {
                    "node_id": node.node_id,
                    "label": node.label,
                    "entity_type": node.entity_type.value,
                }
                for node in graph.nodes
                if node.kind is KnowledgeNodeKind.ENTITY
                and node.entity_type is not None
            ],
            **common,
        )
        await self._driver.execute_query(
            _UPSERT_EXTERNAL_SOURCES,
            nodes=[
                {"node_id": node.node_id, "label": node.label}
                for node in graph.nodes
                if node.kind is KnowledgeNodeKind.EXTERNAL_SOURCE
            ],
            **common,
        )
        await self._driver.execute_query(
            _UPSERT_RELATIONS,
            relations=[
                {
                    "edge_id": relation.edge_id,
                    "source_node_id": relation.source_node_id,
                    "target_node_id": relation.target_node_id,
                    "relation_type": relation.relation_type.value,
                    "predicate": relation.predicate,
                    "evidence_quotes": list(relation.evidence_quotes),
                    "evidence_source_ref_ids": list(relation.evidence_source_ref_ids),
                }
                for relation in graph.relations
            ],
            **common,
        )
        await self._driver.execute_query(
            _UPSERT_MENTIONS,
            mentions=[
                {
                    "mention_id": mention.mention_id,
                    "node_id": mention.node_id,
                    "reading_block_id": mention.reading_block_id,
                    "source_ref_ids": list(mention.source_ref_ids),
                    "evidence_quote": mention.evidence_quote,
                }
                for mention in graph.mentions
            ],
            **common,
        )
        result = await self._driver.execute_query(_PUBLISH, **common)
        if not result.records:
            raise KnowledgeGraphRevisionSupersededError(
                f"content revision {graph.content_revision} was superseded"
            )
        await self._driver.execute_query(_DELETE_OLD_RELATIONS, **common)
        await self._driver.execute_query(_DELETE_OLD_MENTIONS, **common)
        await self._driver.execute_query(
            _DELETE_ORPHAN_NODES,
            database_=self._database,
        )

    async def skip(
        self,
        *,
        resource_id: str,
        content_revision: str,
        document_version: int,
    ) -> None:
        common = {
            "resource_id": resource_id,
            "content_revision": content_revision,
            "document_version": document_version,
            "database_": self._database,
        }
        await self.begin_build(
            resource_id=resource_id,
            content_revision=content_revision,
            document_version=document_version,
        )
        await self._driver.execute_query(
            _DELETE_OLD_RELATIONS,
            graph_revision="",
            **common,
        )
        await self._driver.execute_query(
            _DELETE_OLD_MENTIONS,
            graph_revision="",
            **common,
        )
        result = await self._driver.execute_query(_SKIP, **common)
        if not result.records:
            raise KnowledgeGraphRevisionSupersededError(
                f"content revision {content_revision} was superseded"
            )
        await self._driver.execute_query(
            _DELETE_ORPHAN_NODES,
            database_=self._database,
        )

    async def delete_resources(self, resource_ids: Sequence[str]) -> None:
        ids = list(dict.fromkeys(resource_ids))
        if not ids:
            return
        await self._driver.execute_query(
            _DELETE_RESOURCES,
            resource_ids=ids,
            database_=self._database,
        )
        await self._driver.execute_query(
            _DELETE_ORPHAN_NODES,
            database_=self._database,
        )
        await self._driver.execute_query(
            _DELETE_ORPHAN_GROUP_ACLS,
            database_=self._database,
        )

    async def find_nodes(
        self,
        *,
        evidence: Sequence[SourceEvidence],
        permission_scope: PermissionScope,
        limit: int,
    ) -> list[KnowledgeNode]:
        if not evidence or limit <= 0:
            return []

        query_evidence = [
            {
                "resource_id": record.revision.resource_id,
                "content_revision": record.revision.content_revision,
                "source_ref_id": record.source_ref.ref_id,
            }
            for record in evidence
        ]
        query_evidence = list(
            {tuple(sorted(item.items())): item for item in query_evidence}.values()
        )
        acl_filter, acl_parameters = _acl_predicate(
            permission_scope,
            resource_alias="resource",
        )
        result = await self._driver.execute_query(
            _FIND_NODES.format(acl_filter=acl_filter),
            evidence=query_evidence,
            limit=limit,
            published_status=GraphStatus.PUBLISHED.value,
            **acl_parameters,
            database_=self._database,
            routing_=RoutingControl.READ,
        )
        return [_to_knowledge_node(record) for record in result.records]

    async def find_paths(
        self,
        request: GraphTraversalRequest,
    ) -> list[TraversedPath]:
        if not request.seed_node_ids or request.limit <= 0:
            return []
        pattern = _PATH_PATTERNS.get((request.direction, request.max_depth))
        if pattern is None:
            raise ValueError("graph traversal depth must be 1 or 2")

        evidence_acl, acl_parameters = _acl_predicate(
            request.permission_scope,
            resource_alias="evidence",
        )
        path_node_acl, _ = _acl_predicate(
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
        return [_to_path(record) for record in result.records]


def _to_path(record) -> TraversedPath:
    return TraversedPath(
        nodes=[_to_knowledge_node(item) for item in record["nodes"]],
        edges=[_to_edge(item) for item in record["edges"]],
    )


def _to_knowledge_node(item) -> KnowledgeNode:
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


def _to_edge(item) -> TraversedEdge:
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


def _acl_predicate(
    scope: PermissionScope,
    *,
    resource_alias: str,
) -> tuple[str, dict[str, object]]:
    """生成与 ResourceAcl.can_read 同语义的 Neo4j 查询条件。"""
    return (
        f"""(
          {resource_alias}.owner_id = $acl_user_id
          OR $acl_user_id IN coalesce({resource_alias}.readable_users, [])
          OR (
            NOT $acl_user_id IN coalesce({resource_alias}.excluded_read_users, [])
            AND (
              EXISTS {{
                MATCH ({resource_alias})-[:RAG_V2_HAS_GROUP_ACL]->(managed:RagV2ResourceGroupAcl)
                WHERE managed.group_id IN $acl_managed_group_ids
              }}
              OR EXISTS {{
                MATCH ({resource_alias})-[:RAG_V2_HAS_GROUP_ACL]->(joined:RagV2ResourceGroupAcl)
                WHERE joined.group_id IN $acl_joined_group_ids
                  AND (
                    (joined.is_readable = true
                     AND NOT $acl_user_id IN coalesce(joined.excluded_read_users, []))
                    OR (joined.is_readable = false
                        AND $acl_user_id IN coalesce(joined.readable_users, []))
                  )
              }}
            )
          )
        )""",
        {
            "acl_user_id": scope.user_id,
            "acl_managed_group_ids": list(scope.managed_group_ids),
            "acl_joined_group_ids": list(scope.joined_group_ids),
        },
    )
