from dataclasses import dataclass

import pytest

from rag.application.rag.acl import PermissionAuthorizer
from rag.core.persistence.neo4j import Neo4jMentionLookup
from rag.domain.models.acl import PermissionScope, ResourceAcl
from rag.domain.models.content import ContentRevision
from rag.domain.models.structure import Section, StructureMode
from rag.domain.models.evidence import EvidenceRecord
from rag.domain.models.graph import KnowledgeEntityType, KnowledgeNodeKind
from rag.domain.models.content import ReadingBlock
from rag.domain.models.retrieval import SourceRef
from rag.utils.chunkers import SourceSpan


@dataclass
class _Result:
    records: list[dict]


class _Driver:
    def __init__(self, records=None) -> None:
        self.records = records or []
        self.calls = []

    async def execute_query(self, query, **parameters):
        self.calls.append((query, parameters))
        return _Result(self.records)


class _AclReader:
    def __init__(self, readable_resource_ids) -> None:
        self.readable_resource_ids = set(readable_resource_ids)

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
async def test_lookup_filters_published_revision_deduplicates_and_limits() -> None:
    driver = _Driver(
        [
            {
                "node_id": "node-1",
                "kind": "Entity",
                "label": "Alpha",
                "entity_type": "concept",
                "resource_id": None,
            }
        ]
    )
    lookup = Neo4jMentionLookup(
        driver=driver,
        database="rag-v2",
        authorizer=PermissionAuthorizer(reader=_AclReader({"resource-1"})),
    )
    evidence = _evidence()

    nodes = await lookup.find_nodes(
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
async def test_lookup_does_not_query_without_permission() -> None:
    driver = _Driver()
    lookup = Neo4jMentionLookup(
        driver=driver,
        database="rag-v2",
        authorizer=PermissionAuthorizer(reader=_AclReader(set())),
    )

    nodes = await lookup.find_nodes(
        evidence=[_evidence()],
        permission_scope=PermissionScope(user_id="user-1"),
        limit=3,
    )

    assert nodes == []
    assert driver.calls == []


def _evidence() -> EvidenceRecord:
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
    return EvidenceRecord(
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
