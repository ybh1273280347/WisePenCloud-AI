"""从 Neo4j 已发布图中解析已核验证据对应的节点。"""

from collections.abc import Sequence

from neo4j import AsyncDriver, RoutingControl

from rag.application.rag.acl import PermissionAuthorizer
from rag.application.rag.locate.ports import MentionLookup
from rag.domain.acl import PermissionScope
from rag.domain.evidence import EvidenceRecord
from rag.domain.knowledge_graph import (
    GraphStatus,
    KnowledgeEntityType,
    KnowledgeNode,
    KnowledgeNodeKind,
)

from .acl_predicate import acl_predicate

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


class Neo4jMentionLookup(MentionLookup):
    """先执行统一 ACL，再按 SourceRef 查询当前 published graph。"""

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

    async def find_nodes(
        self,
        *,
        evidence: Sequence[EvidenceRecord],
        permission_scope: PermissionScope,
        limit: int,
    ) -> list[KnowledgeNode]:
        if not evidence or limit <= 0:
            return []

        readable_resource_ids = set(
            await self._authorizer.readable_resource_ids(
                (record.revision.resource_id for record in evidence),
                scope=permission_scope,
            )
        )
        query_evidence = [
            {
                "resource_id": record.revision.resource_id,
                "content_revision": record.revision.content_revision,
                "source_ref_id": record.source_ref.ref_id,
            }
            for record in evidence
            if record.revision.resource_id in readable_resource_ids
        ]
        query_evidence = list(
            {tuple(sorted(item.items())): item for item in query_evidence}.values()
        )
        if not query_evidence:
            return []

        acl_filter, acl_parameters = acl_predicate(
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
        return [_to_node(record) for record in result.records]


def _to_node(record) -> KnowledgeNode:
    kind = KnowledgeNodeKind(record["kind"])
    entity_type = (
        KnowledgeEntityType(record["entity_type"])
        if kind is KnowledgeNodeKind.ENTITY
        else None
    )
    return KnowledgeNode(
        node_id=record["node_id"],
        kind=kind,
        label=record["label"],
        entity_type=entity_type,
        resource_id=(
            record["resource_id"]
            if kind is KnowledgeNodeKind.RESOURCE
            else None
        ),
    )
