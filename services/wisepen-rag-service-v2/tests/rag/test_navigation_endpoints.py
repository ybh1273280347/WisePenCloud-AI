import json

import pytest
from common.core.domain import GroupRoleType
from common.core.exceptions import ServiceException
from common.security import SecurityContextHolder

from rag.api.endpoints.expand import expand_graph
from rag.api.endpoints.locate import locate_candidate
from rag.api.schemas import CandidateLocateRequest, GraphExpandRequest
from rag.application.rag.navigate import (
    DiscoveredKnowledgeNodeView,
    GraphEvidenceRangeView,
    GraphEvidenceRefView,
    GraphEvidenceSectionView,
    GraphExpandResult,
    GraphPathStepView,
    GraphPathView,
    GraphReadingBlockView,
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


def _graph_source() -> GraphEvidenceSectionView:
    return GraphEvidenceSectionView(
        resource_id="resource-1",
        section_id="section-1",
        title="标题",
        section_path="父标题 > 标题",
        reading_blocks=[
            GraphReadingBlockView(
                reading_block_id="block-1",
                text="完整正文",
                page_range="1 - 2",
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
                DiscoveredKnowledgeNodeView(
                    "node-2",
                    "Beta",
                    KnowledgeNodeKind.ENTITY,
                    evidence=[
                        GraphEvidenceRefView(
                            evidence_id="node-evidence-1",
                            resource_id="resource-1",
                            reading_block_id="block-1",
                            quote="正文",
                            range=GraphEvidenceRangeView(2, 4),
                        )
                    ],
                ),
            ],
            paths=[
                GraphPathView(
                    text='("Alpha")-[:DEPENDS_ON]->("Beta")',
                    node_ids=["node-1", "node-2"],
                    steps=[
                        GraphPathStepView(
                            relation='("Alpha")-[:DEPENDS_ON]->("Beta")',
                            evidence=[
                                GraphEvidenceRefView(
                                    evidence_id="relation-evidence-1",
                                    resource_id="resource-1",
                                    reading_block_id="block-1",
                                    quote="正文",
                                    range=GraphEvidenceRangeView(2, 4),
                                )
                            ],
                        )
                    ],
                )
            ],
            evidence_sections=[_graph_source()],
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
        {
            "evidence_id": "relation-evidence-1",
            "resource_id": "resource-1",
            "reading_block_id": "block-1",
            "quote": "正文",
            "range": {"start_offset": 2, "end_offset": 4},
        }
    ]
    assert payload["discovered_nodes"][0]["evidence"][0]["reading_block_id"] == (
        "block-1"
    )
    graph_block = payload["evidence_sections"][0]["reading_blocks"][0]
    assert graph_block["page_range"] == "1 - 2"
    assert "page_labels" not in graph_block
    serialized = json.dumps(payload)
    assert "chunk_id" not in serialized
    assert "source_ref" not in serialized
    assert "matches" not in serialized
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
