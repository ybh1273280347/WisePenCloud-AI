import pytest
from common.core.domain import GroupRoleType
from common.core.exceptions import ServiceException
from common.security import SecurityContextHolder
from pydantic import ValidationError

from rag.api.endpoints.navigation import expand, locate, read_sections
from rag.api.router import api_router
from rag.api.schemas import (
    ExpandRequest as ExpandHttpRequest,
)
from rag.api.schemas import (
    LocateRequest as LocateHttpRequest,
)
from rag.api.schemas import ReadSectionsRequest
from rag.application.rag.expand import GraphExpandResult, UnknownSeedNodeError
from rag.application.rag.expand.graph_traversal import TraversedEdge, TraversedPath
from rag.application.rag.locate import (
    LocatedEvidence,
    LocatedSection,
    LocateError,
    LocateResult,
)
from rag.application.rag.read import (
    SectionAccessRevokedError,
    SectionNotDiscoveredError,
)
from rag.domain.content_revision import ContentRevision
from rag.domain.document_structure import Section, StructureMode
from rag.domain.error_codes import RagErrorCode
from rag.domain.evidence import EvidenceRecord, EvidenceRevisionError
from rag.domain.knowledge_graph import (
    KnowledgeEntityType,
    KnowledgeNode,
    KnowledgeNodeKind,
    KnowledgeRelationType,
)
from rag.domain.navigation import NavigationStateNotFoundError
from rag.application.rag.read import SectionContent, SectionFrontier
from rag.domain.reading import ReadingBlock
from rag.domain.retrieval import SourceRef
from rag.utils.chunkers import SourceSpan
from rag.utils.ranking import RankDecision


class _Locator:
    def __init__(self, result=None, error=None) -> None:
        self.result = result
        self.error = error
        self.request = None

    async def locate(self, request):
        self.request = request
        if self.error is not None:
            raise self.error
        return self.result


class _SectionReader:
    def __init__(self, result=None, error=None) -> None:
        self.result = result
        self.error = error
        self.permission_scope = None

    async def get(self, **kwargs):
        self.permission_scope = kwargs["permission_scope"]
        if self.error is not None:
            raise self.error
        return self.result


class _Expander:
    def __init__(self, result=None, error=None) -> None:
        self.result = result
        self.error = error
        self.request = None

    async def expand(self, request):
        self.request = request
        if self.error is not None:
            raise self.error
        return self.result


def _section() -> Section:
    return Section(
        section_id="section-1",
        title="标题",
        level=1,
        parent_section_id=None,
        ordinal=0,
        section_path=["标题"],
        own_span=SourceSpan(0, 8),
        subtree_span=SourceSpan(0, 8),
        preview="正文",
    )


def _evidence() -> EvidenceRecord:
    section = _section()
    return EvidenceRecord(
        revision=ContentRevision(
            resource_id="resource-1",
            content_revision="revision-1",
            document_version=1,
            content_hash="hash",
            index_schema_version="v1",
            structure_mode=StructureMode.SECTIONED,
            total_length=8,
        ),
        source_ref=SourceRef(
            ref_id="ref-1",
            resource_id="resource-1",
            content_revision="revision-1",
            chunk_id="chunk-1",
            reading_block_id="block-1",
            section_id=section.section_id,
            section_path=list(section.section_path),
            source_spans=[SourceSpan(0, 2)],
            page_labels=["1"],
            anchor_labels=["table-1"],
        ),
        reading_block=ReadingBlock(
            block_id="block-1",
            section_id=section.section_id,
            ordinal=0,
            raw_text="正文",
            source_spans=[SourceSpan(0, 2)],
        ),
        section=section,
        source_text="正文",
    )


def test_navigation_request_constraints_and_identity_boundary() -> None:
    with pytest.raises(ValidationError):
        LocateHttpRequest(
            session_id="session-1",
            semantic_query="问题",
            user_id="forged-user",
        )
    with pytest.raises(ValidationError):
        ReadSectionsRequest(
            session_id="session-1",
            state_id="state-1",
            section_ids=[str(index) for index in range(13)],
        )
    with pytest.raises(ValidationError):
        ExpandHttpRequest(
            session_id="session-1",
            state_id="state-1",
            seed_node_ids=["node-1"],
            max_depth=3,
        )


def test_router_exposes_navigation_endpoints() -> None:
    paths = {
        route.path
        for route in api_router.routes
        if route.path.startswith("/knowledge-navigation/")
    }
    assert paths == {
        "/knowledge-navigation/locate",
        "/knowledge-navigation/sections",
        "/knowledge-navigation/expand",
    }


@pytest.mark.asyncio
async def test_locate_uses_authenticated_identity_and_serializes_sections() -> None:
    section = _section()
    locator = _Locator(
        LocateResult(
            state_id="state-1",
            decision=RankDecision.RELEVANT,
            nodes=[
                KnowledgeNode(
                    node_id="node-1",
                    kind=KnowledgeNodeKind.ENTITY,
                    label="主题",
                )
            ],
            sections=[
                LocatedSection(
                    resource_id="resource-1",
                    content_revision="revision-1",
                    section=section,
                    frontier=SectionFrontier(),
                    evidence=[
                        LocatedEvidence(
                            source_ref_id="ref-1",
                            reading_block_id="block-1",
                            source_text="正文",
                        )
                    ],
                )
            ],
        )
    )
    SecurityContextHolder.set_group_role_map('{"group-1": 1}')

    response = await locate(
        LocateHttpRequest(session_id="session-1", semantic_query="问题"),
        user_id="trusted-user",
        locator=locator,
    )

    assert locator.request.permission_scope.user_id == "trusted-user"
    assert locator.request.permission_scope.group_roles == {
        "group-1": GroupRoleType.ADMIN
    }
    assert response.data.decision is RankDecision.RELEVANT
    assert response.data.nodes[0].node_id == "node-1"
    assert response.data.sections[0].evidence[0].source_ref_id == "ref-1"


@pytest.mark.asyncio
async def test_read_sections_serializes_empty_section_without_reason() -> None:
    section = _section()
    response = await read_sections(
        ReadSectionsRequest(
            session_id="session-1",
            state_id="state-1",
            section_ids=[section.section_id],
        ),
        user_id="user-1",
        reader=_SectionReader(
            {section.section_id: SectionContent(section=section)}
        ),
    )

    payload = response.data.model_dump(mode="json")
    assert payload["sections"][section.section_id]["reading_blocks"] == []
    assert "reason" not in payload["sections"][section.section_id]


@pytest.mark.asyncio
async def test_expand_serializes_nodes_edges_paths_and_sources() -> None:
    source = KnowledgeNode(
        node_id="node-1",
        kind=KnowledgeNodeKind.ENTITY,
        label="Alpha",
        entity_type=KnowledgeEntityType.CONCEPT,
    )
    target = KnowledgeNode(
        node_id="node-2",
        kind=KnowledgeNodeKind.ENTITY,
        label="Beta",
        entity_type=KnowledgeEntityType.CONCEPT,
    )
    edge = TraversedEdge(
        edge_id="edge-1",
        source_node_id=source.node_id,
        target_node_id=target.node_id,
        relation_type=KnowledgeRelationType.RELATED_TO,
        predicate="related",
        evidence_resource_id="resource-1",
        source_content_revision="revision-1",
        evidence_quotes=["正文"],
        evidence_source_ref_ids=["ref-1"],
    )
    path = TraversedPath(nodes=[source, target], edges=[edge])
    expander = _Expander(
        GraphExpandResult(
            state_id="state-1",
            nodes=[source, target],
            edges=[edge],
            paths=[path],
            evidence=[_evidence()],
        )
    )

    response = await expand(
        ExpandHttpRequest(
            session_id="session-1",
            state_id="state-1",
            seed_node_ids=[source.node_id],
            direction="out",
            max_depth=2,
        ),
        user_id="user-1",
        expander=expander,
    )

    assert expander.request.permission_scope.user_id == "user-1"
    assert expander.request.direction.value == "out"
    assert response.data.paths[0].edges[0].edge_id == "edge-1"
    assert response.data.sources[0].ref_id == "ref-1"
    assert response.data.sources[0].source_spans[0].end_offset == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("endpoint", "payload", "dependency_name", "error", "expected"),
    [
        (
            locate,
            LocateHttpRequest(session_id="session-1", semantic_query="问题"),
            "locator",
            LocateError("invalid"),
            RagErrorCode.NAVIGATION_INVALID,
        ),
        (
            read_sections,
            ReadSectionsRequest(
                session_id="session-1",
                state_id="state-1",
                section_ids=["section-1"],
            ),
            "reader",
            NavigationStateNotFoundError("state-1"),
            RagErrorCode.NAVIGATION_STATE_NOT_FOUND,
        ),
        (
            read_sections,
            ReadSectionsRequest(
                session_id="session-1",
                state_id="state-1",
                section_ids=["section-1"],
            ),
            "reader",
            SectionAccessRevokedError("resource-1"),
            RagErrorCode.NAVIGATION_STATE_INVALIDATED,
        ),
        (
            read_sections,
            ReadSectionsRequest(
                session_id="session-1",
                state_id="state-1",
                section_ids=["unknown"],
            ),
            "reader",
            SectionNotDiscoveredError("unknown"),
            RagErrorCode.NAVIGATION_INVALID,
        ),
        (
            expand,
            ExpandHttpRequest(
                session_id="session-1",
                state_id="state-1",
                seed_node_ids=["node-1"],
            ),
            "expander",
            UnknownSeedNodeError("node-1"),
            RagErrorCode.NAVIGATION_INVALID,
        ),
        (
            expand,
            ExpandHttpRequest(
                session_id="session-1",
                state_id="state-1",
                seed_node_ids=["node-1"],
            ),
            "expander",
            EvidenceRevisionError("revision-1"),
            RagErrorCode.NAVIGATION_STATE_INVALIDATED,
        ),
        (
            locate,
            LocateHttpRequest(session_id="session-1", semantic_query="问题"),
            "locator",
            RuntimeError("database details"),
            RagErrorCode.NAVIGATION_FAILED,
        ),
    ],
)
async def test_navigation_error_mapping(
    endpoint,
    payload,
    dependency_name,
    error,
    expected,
) -> None:
    dependency = {
        "locator": _Locator,
        "reader": _SectionReader,
        "expander": _Expander,
    }[dependency_name](error=error)

    with pytest.raises(ServiceException) as raised:
        await endpoint(
            payload,
            user_id="user-1",
            **{dependency_name: dependency},
        )

    assert raised.value.code == expected.code
    assert raised.value.msg == expected.msg
