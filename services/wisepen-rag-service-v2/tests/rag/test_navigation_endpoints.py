import pytest
from common.core.domain import GroupRoleType
from common.core.exceptions import ServiceException
from common.security import SecurityContextHolder

from rag.api.endpoints.expand import expand_graph
from rag.api.endpoints.locate import locate_candidate
from rag.api.schemas import CandidateLocateRequest, GraphExpandRequest
from rag.application.rag.navigate import (
    GraphEvidenceView,
    GraphExpandResult,
    GraphPathStepView,
    GraphPathView,
    KnowledgeNodeView,
    LocateError,
    LocateResult,
    MatchRangeView,
    RetrievalMatchView,
    RetrievalReadingBlockView,
    RetrievedSectionView,
    UnknownSeedNodeError,
)
from rag.domain.error_codes import RagErrorCode
from rag.domain.models.graph import (
    KnowledgeNodeKind,
)
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


def _source() -> RetrievedSectionView:
    return RetrievedSectionView(
        resource_id="resource-1",
        section_id="section-1",
        title="标题",
        section_path="父标题 > 标题",
        reading_blocks=[
            RetrievalReadingBlockView(
                reading_block_id="block-1",
                text="完整正文",
                page_range="1 - 2",
                matches=[
                    RetrievalMatchView(
                        chunk_id="chunk-1",
                        source_ref_id="ref-1",
                        ranges=[MatchRangeView(0, 2)],
                    )
                ],
            )
        ],
    )


@pytest.mark.asyncio
async def test_locate_endpoint_uses_authenticated_identity_and_compact_contract() -> None:
    locator = _Locator(
        LocateResult(
            state_id="state-1",
            retrieval_status=RankDecision.RELEVANT,
            nodes=[
                KnowledgeNodeView(
                    node_id="node-1",
                    label="主题",
                    kind=KnowledgeNodeKind.ENTITY,
                )
            ],
            sections=[_source()],
        )
    )
    SecurityContextHolder.set_group_role_map('{"group-1": 1}')

    response = await locate_candidate(
        CandidateLocateRequest(session_id="session-1", semantic_query="问题"),
        user_id="trusted-user",
        locator=locator,
    )

    assert locator.request.permission_scope.user_id == "trusted-user"
    assert locator.request.permission_scope.group_roles == {
        "group-1": GroupRoleType.ADMIN
    }
    payload = response.data.model_dump(mode="json")
    assert payload["retrieval_status"] == "relevant"
    assert payload["sections"][0]["title"] == "标题"
    assert payload["sections"][0]["reading_blocks"][0]["text"] == "完整正文"
    assert payload["sections"][0]["reading_blocks"][0]["page_range"] == "1 - 2"
    assert "decision" not in payload
    assert "level" not in payload["sections"][0]


@pytest.mark.asyncio
async def test_graph_endpoint_returns_llm_readable_paths_and_evidence_sections() -> None:
    expander = _Expander(
        GraphExpandResult(
            state_id="state-1",
            discovered_nodes=[
                KnowledgeNodeView("node-1", "Alpha", KnowledgeNodeKind.ENTITY),
                KnowledgeNodeView("node-2", "Beta", KnowledgeNodeKind.ENTITY),
            ],
            paths=[
                GraphPathView(
                    text='("Alpha")-[:DEPENDS_ON]->("Beta")',
                    node_ids=["node-1", "node-2"],
                    steps=[
                        GraphPathStepView(
                            relation='("Alpha")-[:DEPENDS_ON]->("Beta")',
                            evidence=[
                                GraphEvidenceView(
                                    quote="正文",
                                    source_ref_ids=["ref-1"],
                                )
                            ],
                        )
                    ],
                )
            ],
            evidence_sections=[_source()],
        )
    )

    response = await expand_graph(
        GraphExpandRequest(
            session_id="session-1",
            state_id="state-1",
            seed_node_ids=["node-1"],
            query="扩展问题",
        ),
        user_id="user-1",
        expander=expander,
    )

    payload = response.data.model_dump(mode="json")
    assert payload["paths"][0]["text"] == '("Alpha")-[:DEPENDS_ON]->("Beta")'
    assert payload["paths"][0]["steps"][0]["evidence"] == [
        {"quote": "正文", "source_ref_ids": ["ref-1"]}
    ]
    assert payload["evidence_sections"][0]["reading_blocks"][0]["matches"][0][
        "source_ref_id"
    ] == "ref-1"
    assert "nodes" not in payload
    assert "edges" not in payload
    assert "sources" not in payload
    assert "edge_ids" not in payload["paths"][0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("endpoint", "payload", "dependency_name", "error", "expected"),
    [
        (
            locate_candidate,
            CandidateLocateRequest(session_id="session-1", semantic_query="问题"),
            "locator",
            LocateError("invalid"),
            RagErrorCode.NAVIGATION_INVALID,
        ),
        (
            expand_graph,
            GraphExpandRequest(
                session_id="session-1",
                state_id="state-1",
                seed_node_ids=["node-1"],
                query="扩展问题",
            ),
            "expander",
            UnknownSeedNodeError("node-1"),
            RagErrorCode.NAVIGATION_INVALID,
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
        "expander": _Expander,
    }[dependency_name](error=error)

    with pytest.raises(ServiceException) as raised:
        await endpoint(
            payload,
            user_id="user-1",
            **{dependency_name: dependency},
        )

    assert raised.value.code == expected.code
