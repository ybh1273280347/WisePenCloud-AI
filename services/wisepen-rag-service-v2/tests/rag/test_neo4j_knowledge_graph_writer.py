from dataclasses import dataclass

import pytest

from rag.core.persistence.neo4j import Neo4jKnowledgeGraphWriter
from rag.domain.knowledge_graph import (
    KnowledgeGraph,
    KnowledgeNode,
    KnowledgeNodeKind,
)
from rag.domain.repositories import KnowledgeGraphRevisionSupersededError


@dataclass
class _Result:
    records: list[dict]


class _Driver:
    def __init__(self, *, cas_succeeds: bool = True) -> None:
        self.cas_succeeds = cas_succeeds
        self.calls: list[tuple[str, dict]] = []

    async def execute_query(self, query: str, **parameters):
        self.calls.append((query, parameters))
        if "graph_status = 'published'" in query and not self.cas_succeeds:
            return _Result(records=[])
        if "RETURN resource.resource_id AS resource_id" in query:
            return _Result(
                records=[{"resource_id": "resource-1"}]
            )
        return _Result(records=[])


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


@pytest.mark.asyncio
async def test_writer_uses_v2_namespace_and_publishes_last() -> None:
    driver = _Driver()
    writer = Neo4jKnowledgeGraphWriter(driver=driver, database="rag-v2")

    await writer.begin_build(
        resource_id="resource-1",
        content_revision="revision-1",
        document_version=3,
    )
    await writer.publish(graph=_graph(), document_version=3)

    queries = [query for query, _ in driver.calls]
    assert "RagV2ResourceNode" in queries[0]
    assert any("RAG_V2_KNOWLEDGE_RELATION" in query for query in queries)
    relation_call = next(
        parameters
        for query, parameters in driver.calls
        if "UNWIND $relations" in query
    )
    assert all("relation_id" not in item for item in relation_call["relations"])
    assert any("RAG_V2_MENTION" in query for query in queries)
    publish_index = next(
        index for index, query in enumerate(queries) if "graph_status = 'published'" in query
    )
    assert publish_index == max(
        index for index, query in enumerate(queries) if "RETURN resource.resource_id" in query
    )
    assert all(parameters["database_"] == "rag-v2" for _, parameters in driver.calls)


@pytest.mark.asyncio
async def test_writer_rejects_superseded_publish() -> None:
    driver = _Driver(cas_succeeds=False)
    writer = Neo4jKnowledgeGraphWriter(driver=driver, database="rag-v2")

    with pytest.raises(KnowledgeGraphRevisionSupersededError):
        await writer.publish(graph=_graph(), document_version=3)


@pytest.mark.asyncio
async def test_writer_skips_revision_after_clearing_old_graph() -> None:
    driver = _Driver()
    writer = Neo4jKnowledgeGraphWriter(driver=driver, database="rag-v2")

    await writer.skip(
        resource_id="resource-1",
        content_revision="revision-flat",
        document_version=4,
    )

    queries = [query for query, _ in driver.calls]
    skip_index = next(
        index for index, query in enumerate(queries) if "graph_status = 'skipped'" in query
    )
    assert skip_index > 0
    assert any("DELETE relation" in query for query in queries)
    assert any("DELETE mention" in query for query in queries)
    assert "graph_status = 'skipped'" in queries[skip_index]
