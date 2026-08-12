import pytest

from rag.application.rag.expand import (
    GraphExpandRequest,
    KnowledgeGraphExpander,
    UnknownSeedNodeError,
)
from rag.application.rag.expand.ports import TraversedEdge, TraversedPath
from rag.domain.acl import PermissionScope
from rag.domain.knowledge_graph import (
    KnowledgeNode,
    KnowledgeNodeKind,
    KnowledgeRelationType,
)
from rag.domain.navigation import NavigationState
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
            root_query="根问题",
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
    def __init__(self) -> None:
        self.calls = []

    async def verify_refs(self, **kwargs):
        self.calls.append(kwargs)
        return []


@pytest.mark.asyncio
async def test_expand_ranks_verifies_and_adds_only_new_nodes() -> None:
    traversal = _Traversal([_path()])
    ranking = _RankingPipeline()
    verifier = _EvidenceVerifier()
    state_store = _StateStore()
    expander = KnowledgeGraphExpander(
        traversal=traversal,
        ranking_pipeline=ranking,
        evidence_verifier=verifier,
        state_store=state_store,
    )

    result = await expander.expand(_request())

    assert ranking.request.query.text == "根问题"
    assert traversal.request.seed_node_ids == ["node-a"]
    assert verifier.calls[0]["source_ref_ids"] == ["ref-1"]
    assert state_store.calls[0]["node_ids"] == ["node-b"]
    assert [node.node_id for node in result.nodes] == ["node-a", "node-b"]


@pytest.mark.asyncio
async def test_expand_rejects_unknown_seed() -> None:
    expander = KnowledgeGraphExpander(
        traversal=_Traversal([]),
        ranking_pipeline=_RankingPipeline(),
        evidence_verifier=_EvidenceVerifier(),
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
        evidence_verifier=_EvidenceVerifier(),
        state_store=_StateStore(added=[]),
    )

    result = await expander.expand(_request())

    assert result.paths == []
    assert result.nodes == []


def _request() -> GraphExpandRequest:
    return GraphExpandRequest(
        state_id="nav-1",
        session_id="session-1",
        permission_scope=PermissionScope(user_id="user-1"),
        seed_node_ids=["node-a"],
    )


def _path() -> TraversedPath:
    return TraversedPath(
        nodes=[
            KnowledgeNode(
                node_id="node-a",
                kind=KnowledgeNodeKind.ENTITY,
                label="Alpha",
            ),
            KnowledgeNode(
                node_id="node-b",
                kind=KnowledgeNodeKind.ENTITY,
                label="Beta",
            ),
        ],
        edges=[
            TraversedEdge(
                edge_id="edge-1",
                source_node_id="node-a",
                target_node_id="node-b",
                relation_type=KnowledgeRelationType.DEPENDS_ON,
                evidence_resource_id="resource-1",
                source_content_revision="revision-1",
                evidence_quotes=["Alpha depends on Beta."],
                evidence_source_ref_ids=["ref-1"],
            )
        ],
    )
