import pytest

from rag.application.rag.navigate import (
    GraphExpandRequest,
    KnowledgeGraphExpander,
    UnknownSeedNodeError,
)
from rag.application.rag.navigate.graph_expander import _render_path, _to_path_view
from rag.domain.models.acl import PermissionScope
from rag.domain.models.content import ContentRevision, ReadingBlock
from rag.domain.models.evidence import EvidenceRecord
from rag.domain.models.graph import (
    KnowledgeNode,
    KnowledgeNodeKind,
    KnowledgeRelationType,
    TraversedEdge,
    TraversedPath,
)
from rag.domain.models.navigation import NavigationState
from rag.domain.models.retrieval import SourceRef
from rag.domain.models.structure import Section, StructureMode
from rag.utils.chunkers import SourceSpan
from rag.utils.ranking import RankCandidate, RankedCandidate, RankResult


class _StateStore:
    def __init__(self, *, added=None) -> None:
        self.added = ["node-b"] if added is None else added
        self.calls = []

    async def get(self, state_id):
        return NavigationState(
            state_id=state_id,
            user_id="user-1",
            session_id="session-1",
            known_node_ids=["node-a"],
        )

    async def add_known_nodes(self, **kwargs):
        self.calls.append(kwargs)
        return self.added


class _Traversal:
    def __init__(self, paths) -> None:
        self.paths = paths
        self.request = None

    async def find_paths(self, request):
        self.request = request
        return self.paths


class _RankingPipeline:
    def __init__(self) -> None:
        self.request = None

    async def arank(self, request):
        self.request = request
        return RankResult(
            ranked=tuple(
                RankedCandidate(
                    candidate=RankCandidate(candidate_id=candidate.candidate_id),
                    rank=index,
                    score=1.0,
                )
                for index, candidate in enumerate(request.candidates, 1)
            ),
            total_candidates=len(request.candidates),
        )


class _EvidenceVerifier:
    def __init__(self, records=None) -> None:
        self.records = {
            record.source_ref.ref_id: record for record in (records or [])
        }
        self.calls = []

    async def verify_graph_evidence_refs(self, **kwargs):
        self.calls.append(kwargs)
        return [self.records[ref_id] for ref_id in kwargs["source_ref_ids"]]


class _Authorizer:
    async def readable_resource_ids(self, resource_ids, *, scope):
        return list(resource_ids)


@pytest.mark.asyncio
async def test_expand_ranks_verifies_and_adds_only_new_nodes() -> None:
    traversal = _Traversal([_path()])
    ranking = _RankingPipeline()
    verifier = _EvidenceVerifier([_record()])
    state_store = _StateStore()
    expander = KnowledgeGraphExpander(
        traversal=traversal,
        ranking_pipeline=ranking,
        evidence_verifier=verifier,
        authorizer=_Authorizer(),
        state_store=state_store,
    )

    result = await expander.expand(_request())

    assert ranking.request.query.text == "扩展问题"
    assert traversal.request.seed_node_ids == ["node-a"]
    assert verifier.calls[0]["source_ref_ids"] == ["ref-1"]
    assert state_store.calls[0]["node_ids"] == ["node-b"]
    assert [node.node_id for node in result.discovered_nodes] == ["node-b"]
    assert result.paths[0].text == '("Alpha")-[:DEPENDS_ON]->("Beta")'
    assert result.paths[0].node_ids == ["node-a", "node-b"]
    assert result.paths[0].steps[0].relation == (
        '("Alpha")-[:DEPENDS_ON]->("Beta")'
    )
    assert result.paths[0].steps[0].evidence[0].quote == "Alpha depends on Beta."
    assert result.paths[0].steps[0].evidence[0].source_ref_ids == ["ref-1"]
    assert result.evidence_sections[0].reading_blocks[0].matches[0].source_ref_id == (
        "ref-1"
    )


@pytest.mark.asyncio
async def test_expand_rejects_unknown_seed() -> None:
    expander = KnowledgeGraphExpander(
        traversal=_Traversal([]),
        ranking_pipeline=_RankingPipeline(),
        evidence_verifier=_EvidenceVerifier([_record()]),
        authorizer=_Authorizer(),
        state_store=_StateStore(),
    )

    request = _request()
    request.seed_node_ids = ["unknown"]
    with pytest.raises(UnknownSeedNodeError):
        await expander.expand(request)


@pytest.mark.asyncio
async def test_expand_returns_nothing_when_concurrent_call_added_nodes_first() -> None:
    expander = KnowledgeGraphExpander(
        traversal=_Traversal([_path()]),
        ranking_pipeline=_RankingPipeline(),
        evidence_verifier=_EvidenceVerifier([_record()]),
        authorizer=_Authorizer(),
        state_store=_StateStore(added=[]),
    )

    result = await expander.expand(_request())

    assert result.paths == []
    assert result.discovered_nodes == []
    assert result.evidence_sections == []


def test_render_path_preserves_fact_direction_for_reverse_traversal() -> None:
    path = TraversedPath(
        nodes=[_node("node-b", "Beta"), _node("node-a", "Alpha")],
        edges=[_edge(source="node-a", target="node-b")],
    )

    text, relations = _render_path(path)

    assert text == '("Beta")<-[:DEPENDS_ON]-("Alpha")'
    assert relations == ['("Alpha")-[:DEPENDS_ON]->("Beta")']


def test_render_path_handles_mixed_directions_and_keeps_step_order() -> None:
    path = TraversedPath(
        nodes=[
            _node("node-b", "Beta"),
            _node("node-a", "Alpha"),
            _node("node-c", "Gamma"),
        ],
        edges=[
            _edge(edge_id="edge-1", source="node-a", target="node-b"),
            _edge(
                edge_id="edge-2",
                source="node-a",
                target="node-c",
                relation=KnowledgeRelationType.CAUSES,
            ),
        ],
    )

    text, relations = _render_path(path)

    assert text == '("Beta")<-[:DEPENDS_ON]-("Alpha")-[:CAUSES]->("Gamma")'
    assert relations == [
        '("Alpha")-[:DEPENDS_ON]->("Beta")',
        '("Alpha")-[:CAUSES]->("Gamma")',
    ]


def test_render_path_only_adds_predicate_for_related_to_and_escapes_json() -> None:
    related_path = TraversedPath(
        nodes=[_node("node-a", 'A ("quoted")\nlabel'), _node("node-b", "B")],
        edges=[
            _edge(
                relation=KnowledgeRelationType.RELATED_TO,
                predicate='because "x"\nline',
            )
        ],
    )
    ordinary_path = TraversedPath(
        nodes=[_node("node-a", "A"), _node("node-b", "B")],
        edges=[
            _edge(
                relation=KnowledgeRelationType.CAUSES,
                predicate="must not leak",
            )
        ],
    )

    related_text, _ = _render_path(related_path)
    ordinary_text, _ = _render_path(ordinary_path)

    assert related_text == (
        '("A (\\"quoted\\")\\nlabel")-[:RELATED_TO '
        '{predicate: "because \\"x\\"\\nline"}]->("B")'
    )
    assert ordinary_text == '("A")-[:CAUSES]->("B")'


def test_render_path_rejects_an_edge_that_does_not_join_adjacent_nodes() -> None:
    path = TraversedPath(
        nodes=[_node("node-a", "A"), _node("node-b", "B")],
        edges=[_edge(source="node-x", target="node-y")],
    )

    with pytest.raises(RuntimeError, match="does not connect adjacent"):
        _render_path(path)


def test_path_view_pairs_each_quote_only_with_source_refs_containing_it() -> None:
    edge = _edge(
        evidence_quotes=["first quote", "second quote"],
        evidence_source_ref_ids=["ref-1", "ref-2", "ref-3"],
    )
    path = TraversedPath(
        nodes=[_node("node-a", "A"), _node("node-b", "B")],
        edges=[edge],
    )
    records = [
        _record(ref_id="ref-1", text="first quote and context"),
        _record(ref_id="ref-2", text="second quote and context"),
        _record(ref_id="ref-3", text="unrelated context"),
    ]

    view, retained = _to_path_view(path, {edge.edge_id: records})

    assert [item.quote for item in view.steps[0].evidence] == [
        "first quote",
        "second quote",
    ]
    assert [item.source_ref_ids for item in view.steps[0].evidence] == [
        ["ref-1"],
        ["ref-2"],
    ]
    assert {record.source_ref.ref_id for record in retained} == {"ref-1", "ref-2"}


def _request() -> GraphExpandRequest:
    return GraphExpandRequest(
        state_id="nav-1",
        session_id="session-1",
        permission_scope=PermissionScope(user_id="user-1"),
        seed_node_ids=["node-a"],
        query="扩展问题",
    )


def _path() -> TraversedPath:
    return TraversedPath(
        nodes=[
            _node("node-a", "Alpha"),
            _node("node-b", "Beta"),
        ],
        edges=[_edge()],
    )


def _node(node_id: str, label: str) -> KnowledgeNode:
    return KnowledgeNode(
        node_id=node_id,
        kind=KnowledgeNodeKind.ENTITY,
        label=label,
    )


def _edge(
    *,
    edge_id: str = "edge-1",
    source: str = "node-a",
    target: str = "node-b",
    relation: KnowledgeRelationType = KnowledgeRelationType.DEPENDS_ON,
    predicate: str | None = None,
    evidence_quotes: list[str] | None = None,
    evidence_source_ref_ids: list[str] | None = None,
) -> TraversedEdge:
    return TraversedEdge(
        edge_id=edge_id,
        source_node_id=source,
        target_node_id=target,
        relation_type=relation,
        evidence_resource_id="resource-1",
        source_content_revision="revision-1",
        evidence_quotes=(
            ["Alpha depends on Beta."]
            if evidence_quotes is None
            else evidence_quotes
        ),
        evidence_source_ref_ids=(
            ["ref-1"]
            if evidence_source_ref_ids is None
            else evidence_source_ref_ids
        ),
        predicate=predicate,
    )


def _record(ref_id: str = "ref-1", text: str = "Alpha depends on Beta.") -> EvidenceRecord:
    span = SourceSpan(0, len(text))
    revision = ContentRevision(
        resource_id="resource-1",
        content_revision="revision-1",
        document_version=1,
        content_hash="hash",
        index_schema_version="rag-v2-content:v2",
        structure_mode=StructureMode.SECTIONED,
        total_length=len(text),
    )
    section = Section(
        section_id=f"section-{ref_id}",
        title="测试章节",
        level=1,
        parent_section_id=None,
        ordinal=0,
        section_path=["测试章节"],
        own_span=span,
        subtree_span=span,
        content_spans=[span],
    )
    return EvidenceRecord(
        revision=revision,
        source_ref=SourceRef(
            ref_id=ref_id,
            resource_id="resource-1",
            content_revision="revision-1",
            chunk_id=f"chunk-{ref_id}",
            reading_block_id=f"block-{ref_id}",
            section_id=f"section-{ref_id}",
            section_path=["测试章节"],
            source_spans=[span],
        ),
        reading_block=ReadingBlock(
            block_id=f"block-{ref_id}",
            section_id=f"section-{ref_id}",
            ordinal=0,
            raw_text=text,
            source_spans=[span],
            page_labels=["1"],
        ),
        section=section,
        source_text=text,
    )
