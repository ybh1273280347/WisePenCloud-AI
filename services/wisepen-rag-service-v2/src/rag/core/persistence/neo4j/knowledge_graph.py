"""Neo4j v2 知识图谱写入 adapter。"""

from collections.abc import Sequence

from neo4j import AsyncDriver

from rag.domain.knowledge_graph import (
    GraphStatus,
    KnowledgeGraph,
    KnowledgeNodeKind,
    resource_node_id,
)
from rag.domain.repositories.neo4j.knowledge_graph import (
    KnowledgeGraphRevisionSupersededError,
    KnowledgeGraphWriter,
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


class Neo4jKnowledgeGraphWriter(KnowledgeGraphWriter):
    """将合并后的知识图谱写入 v2 专属 Neo4j namespace。"""

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
                    "evidence_source_ref_ids": list(
                        relation.evidence_source_ref_ids
                    ),
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
