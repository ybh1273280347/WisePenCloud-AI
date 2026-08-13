from dataclasses import dataclass

import pytest

from rag.application.rag.acl import PermissionAuthorizer
from rag.domain.models.graph import (
    GraphTraversalRequest,
    TraversalDirection,
)
from rag.core.persistence.neo4j import Neo4jGraphTraversal
from rag.domain.models.acl import PermissionScope, ResourceAcl
from rag.domain.models.graph import KnowledgeRelationType


@dataclass
class _Result:
    records: list[dict]


class _Driver:
    def __init__(self, records) -> None:
        self.records = records
        self.calls = []

    async def execute_query(self, query, **parameters):
        self.calls.append((query, parameters))
        return _Result(self.records)


class _AclReader:
    def __init__(self, readable_resource_ids) -> None:
        self.readable_resource_ids = set(readable_resource_ids)

    async def get_resource_acl(self, resource_id):
        if resource_id not in self.readable_resource_ids:
            return None
        return ResourceAcl(
            resource_id=resource_id,
            acl_revision=1,
            owner_id="user-1",
        )

    async def get_resource_acls(self, resource_ids):
        return {
            resource_id: ResourceAcl(
                resource_id=resource_id,
                acl_revision=1,
                owner_id="user-1",
            )
            for resource_id in resource_ids
            if resource_id in self.readable_resource_ids
        }


@pytest.mark.asyncio
async def test_traversal_uses_bounded_direction_revision_and_cycle_filter() -> None:
    driver = _Driver([_path_record()])
    traversal = Neo4jGraphTraversal(
        driver=driver,
        database="rag-v2",
        authorizer=PermissionAuthorizer(local_store=_AclReader({"resource-1"})),
    )

    paths = await traversal.find_paths(
        GraphTraversalRequest(
            seed_node_ids=["node-a"],
            permission_scope=PermissionScope(user_id="user-1"),
            relation_types=[KnowledgeRelationType.DEPENDS_ON],
            direction=TraversalDirection.OUT,
            max_depth=2,
            limit=5,
        )
    )

    query, parameters = driver.calls[0]
    assert "*1..2]->(target)" in query
    assert "single(other IN nodes(path)" in query
    assert "evidence.graph_status = 'published'" in query
    assert "evidence.graph_revision = relation.graph_revision" in query
    assert parameters["relation_types"] == ["DEPENDS_ON"]
    assert paths[0].edges[0].edge_id == "edge-1"


@pytest.mark.asyncio
async def test_traversal_drops_path_when_evidence_acl_is_denied() -> None:
    traversal = Neo4jGraphTraversal(
        driver=_Driver([_path_record()]),
        database="rag-v2",
        authorizer=PermissionAuthorizer(local_store=_AclReader(set())),
    )

    paths = await traversal.find_paths(
        GraphTraversalRequest(
            seed_node_ids=["node-a"],
            permission_scope=PermissionScope(user_id="user-1"),
        )
    )

    assert paths == []


def _path_record() -> dict:
    return {
        "nodes": [
            {
                "node_id": "node-a",
                "kind": "Entity",
                "label": "Alpha",
                "entity_type": "concept",
                "resource_id": None,
            },
            {
                "node_id": "node-b",
                "kind": "Entity",
                "label": "Beta",
                "entity_type": "concept",
                "resource_id": None,
            },
        ],
        "edges": [
            {
                "edge_id": "edge-1",
                "source_node_id": "node-a",
                "target_node_id": "node-b",
                "relation_type": "DEPENDS_ON",
                "predicate": None,
                "evidence_resource_id": "resource-1",
                "source_content_revision": "revision-1",
                "evidence_quotes": ["Alpha depends on Beta."],
                "evidence_source_ref_ids": ["ref-1"],
            }
        ],
    }
