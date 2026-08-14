from dataclasses import dataclass

import pytest

from rag.core.persistence.neo4j import Neo4jKnowledgeGraphRepository
from rag.domain.models.acl import PermissionScope
from rag.domain.models.content import ContentRevision, ReadingBlock
from rag.domain.models.graph import (
    GraphTraversalRequest,
    KnowledgeEntityType,
    KnowledgeGraph,
    KnowledgeNode,
    KnowledgeNodeKind,
    KnowledgeRelationType,
    TraversalDirection,
)
from rag.domain.models.provenance import SourceEvidence, SourceRef
from rag.domain.models.structure import Section, StructureMode
from rag.domain.repositories import KnowledgeGraphRevisionSupersededError
from rag.utils.chunkers import SourceSpan


@dataclass
class _Result:
    records: list[dict]


class _Driver:
    def __init__(
        self,
        records: list[dict] | None = None,
        *,
        cas_succeeds: bool = True,
    ) -> None:
        self.records = records or []
        self.cas_succeeds = cas_succeeds
        self.calls: list[tuple[str, dict]] = []

    async def execute_query(self, query: str, **parameters):
        self.calls.append((query, parameters))
        if "graph_status = 'published'" in query and not self.cas_succeeds:
            return _Result(records=[])
        if "RETURN resource.resource_id AS resource_id" in query:
            return _Result(records=[{"resource_id": "resource-1"}])
        return _Result(self.records)


@pytest.mark.asyncio
async def test_repository_initializes_v2_schema() -> None:
    driver = _Driver()
    repository = Neo4jKnowledgeGraphRepository(driver=driver, database="rag-v2")

    await repository.initialize()

    queries = [query for query, _ in driver.calls]
    assert len(queries) == 3
    assert "CREATE CONSTRAINT rag_v2_node_id" in queries[0]
    assert "CREATE INDEX rag_v2_relation_resource" in queries[1]
    assert "CREATE INDEX rag_v2_mention_resource" in queries[2]
    assert all(parameters["database_"] == "rag-v2" for _, parameters in driver.calls)


@pytest.mark.asyncio
async def test_repository_uses_v2_namespace_and_publishes_last() -> None:
    driver = _Driver()
    repository = Neo4jKnowledgeGraphRepository(driver=driver, database="rag-v2")

    await repository.begin_build(
        resource_id="resource-1",
        content_revision="revision-1",
        document_version=3,
    )
    await repository.publish(graph=_graph(), document_version=3)

    queries = [query for query, _ in driver.calls]
    assert "RagV2ResourceNode" in queries[0]
    assert any("RAG_V2_KNOWLEDGE_RELATION" in query for query in queries)
    relation_call = next(
        parameters for query, parameters in driver.calls if "UNWIND $relations" in query
    )
    assert all("relation_id" not in item for item in relation_call["relations"])
    assert any("RAG_V2_MENTION" in query for query in queries)
    publish_index = next(
        index
        for index, query in enumerate(queries)
        if "graph_status = 'published'" in query
    )
    assert publish_index == max(
        index
        for index, query in enumerate(queries)
        if "RETURN resource.resource_id" in query
    )
    assert all(parameters["database_"] == "rag-v2" for _, parameters in driver.calls)


@pytest.mark.asyncio
async def test_repository_rejects_superseded_publish() -> None:
    driver = _Driver(cas_succeeds=False)
    repository = Neo4jKnowledgeGraphRepository(driver=driver, database="rag-v2")

    with pytest.raises(KnowledgeGraphRevisionSupersededError):
        await repository.publish(graph=_graph(), document_version=3)


@pytest.mark.asyncio
async def test_repository_skips_revision_after_clearing_old_graph() -> None:
    driver = _Driver()
    repository = Neo4jKnowledgeGraphRepository(driver=driver, database="rag-v2")

    await repository.skip(
        resource_id="resource-1",
        content_revision="revision-flat",
        document_version=4,
    )

    queries = [query for query, _ in driver.calls]
    skip_index = next(
        index
        for index, query in enumerate(queries)
        if "graph_status = 'skipped'" in query
    )
    assert skip_index > 0
    assert any("DELETE relation" in query for query in queries)
    assert any("DELETE mention" in query for query in queries)
    assert "graph_status = 'skipped'" in queries[skip_index]


@pytest.mark.asyncio
async def test_repository_deletes_resource_group_acl_orphans() -> None:
    driver = _Driver()
    repository = Neo4jKnowledgeGraphRepository(driver=driver, database="rag-v2")

    await repository.delete_resources(["resource-1"])

    queries = [query for query, _ in driver.calls]
    assert "DETACH DELETE resource" in queries[0]
    assert "RagV2ResourceGroupAcl" in queries[-1]


@pytest.mark.asyncio
async def test_find_nodes_filters_published_revision_and_deduplicates() -> None:
    driver = _Driver(
        records=[
            {
                "node_id": "node-1",
                "kind": "Entity",
                "label": "Alpha",
                "entity_type": "concept",
                "resource_id": None,
            }
        ]
    )
    repository = Neo4jKnowledgeGraphRepository(driver=driver, database="rag-v2")
    evidence = _evidence()

    nodes = await repository.find_nodes(
        evidence=[evidence, evidence],
        permission_scope=PermissionScope(user_id="user-1"),
        limit=3,
    )

    query, parameters = driver.calls[0]
    assert "resource.graph_status = $published_status" in query
    assert "resource.owner_id = $acl_user_id" in query
    assert "resource.content_revision = item.content_revision" in query
    assert "mention.graph_revision = resource.graph_revision" in query
    assert parameters["evidence"] == [
        {
            "resource_id": "resource-1",
            "content_revision": "revision-1",
            "source_ref_id": "ref-1",
        }
    ]
    assert parameters["limit"] == 3
    assert parameters["published_status"] == "published"
    assert nodes[0].kind is KnowledgeNodeKind.ENTITY
    assert nodes[0].entity_type is KnowledgeEntityType.CONCEPT


@pytest.mark.asyncio
async def test_find_nodes_does_not_query_when_limit_is_zero() -> None:
    driver = _Driver()
    repository = Neo4jKnowledgeGraphRepository(driver=driver, database="rag-v2")

    nodes = await repository.find_nodes(
        evidence=[_evidence()],
        permission_scope=PermissionScope(user_id="user-1"),
        limit=0,
    )

    assert nodes == []
    assert driver.calls == []


@pytest.mark.asyncio
async def test_find_paths_uses_bounded_direction_revision_and_cycle_filter() -> None:
    driver = _Driver(records=[_path_record()])
    repository = Neo4jKnowledgeGraphRepository(driver=driver, database="rag-v2")

    paths = await repository.find_paths(
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
async def test_find_paths_does_not_query_without_seed_nodes() -> None:
    driver = _Driver(records=[_path_record()])
    repository = Neo4jKnowledgeGraphRepository(driver=driver, database="rag-v2")

    paths = await repository.find_paths(
        GraphTraversalRequest(
            seed_node_ids=[],
            permission_scope=PermissionScope(user_id="user-1"),
        )
    )

    assert paths == []
    assert driver.calls == []


def _graph() -> KnowledgeGraph:
    return KnowledgeGraph(
        resource_id="resource-1",
        content_revision="revision-1",
        graph_revision="graph-1",
        nodes=[
            KnowledgeNode(
                node_id="entity-1",
                kind=KnowledgeNodeKind.ENTITY,
                label="Alpha",
            )
        ],
    )


def _evidence() -> SourceEvidence:
    revision = ContentRevision(
        resource_id="resource-1",
        content_revision="revision-1",
        document_version=1,
        content_hash="hash",
        index_schema_version="v1",
        structure_mode=StructureMode.SECTIONED,
        total_length=5,
    )
    source_span = SourceSpan(0, 5)
    return SourceEvidence(
        revision=revision,
        source_ref=SourceRef(
            ref_id="ref-1",
            resource_id="resource-1",
            content_revision="revision-1",
            chunk_id="chunk-1",
            reading_block_id="block-1",
            section_id="section-1",
            section_path=["Alpha"],
            source_spans=[source_span],
        ),
        reading_block=ReadingBlock(
            block_id="block-1",
            section_id="section-1",
            ordinal=0,
            raw_text="Alpha",
            source_spans=[source_span],
        ),
        section=Section(
            section_id="section-1",
            title="Alpha",
            level=1,
            parent_section_id=None,
            ordinal=0,
            section_path=["Alpha"],
            own_span=source_span,
            subtree_span=source_span,
        ),
        source_text="Alpha",
    )


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
