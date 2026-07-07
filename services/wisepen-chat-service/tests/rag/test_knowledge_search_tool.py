from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

ranking_engine_path = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "chat"
    / "application"
    / "utils"
    / "ranking_engine"
)
ranking_engine_package = types.ModuleType("chat.application.utils.ranking_engine")
ranking_engine_package.__path__ = [str(ranking_engine_path)]
sys.modules["chat.application.utils.ranking_engine"] = ranking_engine_package

registry_module = types.ModuleType("chat.application.utils.ranking_engine.registry")
registry_module.get_ranking_engine = lambda name: None
sys.modules["chat.application.utils.ranking_engine.registry"] = registry_module


class _Settings:
    ZERO_ENTROPY_API_KEY = "test-zero-entropy-key"
    EVIDENCE_RANKER_ZE_MODEL = "test-rerank-model"
    EVIDENCE_RANKER_ZE_TOP_N = 20
    RAG_KNOWLEDGE_SEARCH_TOP_K = 8
    RAG_KNOWLEDGE_SEARCH_CANDIDATE_LIMIT = 80
    RAG_KNOWLEDGE_SEARCH_ELASTIC_PREFILTER_LIMIT = 1000


config_module = types.ModuleType("chat.core.config.app_settings")
config_module.settings = _Settings()
sys.modules["chat.core.config.app_settings"] = config_module

from chat.application.rag.answerability import (  # noqa: E402
    RagAnswerabilityWarning,
    RagAnswerabilityWarningReason,
    RagHardGateDecision,
    RagHardGateStatus,
)
from chat.application.rag.context_builder import (  # noqa: E402
    RagContextPackage,
    RagDirectEvidence,
)
from chat.application.rag.graph import (  # noqa: E402
    RagGraphEnhancementResult,
    RagGraphEvidence,
    RagOntologyHint,
)
from chat.application.rag.models import RagKnowledgeSearchResult  # noqa: E402
from chat.application.rag.retrieval.models import RagRetrievalProfile  # noqa: E402
from chat.application.tools.core.tool_return import ToolReturn  # noqa: E402
from chat.application.tools.rag_tools import RagKnowledgeSearchTool  # noqa: E402


@pytest.mark.anyio
async def test_rag_knowledge_search_tool_maps_model_args_to_acl_safe_request() -> None:
    searcher = _RecordingSearcher(
        result=_search_result(
            direct_evidence=(
                RagDirectEvidence(
                    citation_id="E1",
                    document_version="3",
                    text="请求必须携带 AppBuilder API Key。",
                    page_label="1",
                    section_path=("鉴权",),
                    matched_child_ids=("child-internal",),
                ),
            ),
            graph_evidence=(
                RagGraphEvidence(
                    chunk_id="graph-child-internal",
                    document_version="3",
                    evidence_text="Graph 补充证据。",
                    page_label="2",
                    section_path=("接口",),
                    path=("child-internal", "graph-child-internal"),
                    related_concepts=("API Key",),
                ),
            ),
        )
    )
    tool = RagKnowledgeSearchTool(searcher=searcher)

    output = await tool.execute(
        {"user_id": "user-1", "session_id": "session-1"},
        query="AppBuilder API Key 怎么申请？",
        resource_id="resource-doc",
        retrieval_profile="lexical",
        keywords=["API Key"],
    )

    request = searcher.requests[0]
    assert request.query == "AppBuilder API Key 怎么申请？"
    assert request.resource_id == "resource-doc"
    assert request.retrieval_profile == RagRetrievalProfile.LEXICAL
    assert request.keywords == ("API Key",)
    assert request.permission_scope is not None
    assert request.permission_scope.user_id == "user-1"
    assert request.permission_scope.group_role_map == {}
    assert request.session_id == "session-1"
    assert request.top_k == 8
    assert request.candidate_limit == 80

    assert isinstance(output, ToolReturn)
    assert output.tag == "rag_knowledge_search_result"
    assert output.visible_result["answerability"]["status"] == "passed"
    assert output.visible_result["direct_evidence"][0]["citation_id"] == "E1"
    assert "citation_anchor" not in output.visible_result["direct_evidence"][0]
    assert output.visible_result["direct_evidence"][0]["page_label"] == "1"
    assert output.visible_result["direct_evidence"][0]["section_path"] == ["鉴权"]
    assert "parent-internal" not in output.visible_result["direct_evidence"][0]
    assert "score" not in output.visible_result["direct_evidence"][0]
    assert "matched_child_chunks" not in output.visible_result["direct_evidence"][0]
    assert "citation_anchor" not in output.visible_result["graph_evidence"][0]
    assert output.visible_result["graph_evidence"][0]["page_label"] == "2"
    assert output.visible_result["graph_evidence"][0]["section_path"] == ["接口"]
    assert output.visible_result["graph_evidence"][0]["related_concepts"] == ["API Key"]
    assert len(output.cacheable_texts) == 1
    assert "请求必须携带 AppBuilder API Key" in output.cacheable_texts[0]
    assert "parent-internal" not in output.cacheable_texts[0]
    assert "child-internal" not in output.cacheable_texts[0]
    assert "graph-child-internal" not in output.cacheable_texts[0]


@pytest.mark.anyio
async def test_rag_knowledge_search_tool_returns_no_context_when_hard_gate_rejects() -> None:
    searcher = _RecordingSearcher(
        result=RagKnowledgeSearchResult(
            hard_gate=RagHardGateDecision(
                status=RagHardGateStatus.REJECTED,
            ),
        )
    )
    tool = RagKnowledgeSearchTool(searcher=searcher)

    output = await tool.execute(
        {"user_id": "user-1", "session_id": "session-1"},
        query="没有证据的问题",
        resource_id="resource-doc",
    )

    assert output.visible_result["answerability"]["status"] == "rejected"
    assert output.cacheable_texts == ()


class _RecordingSearcher:
    def __init__(self, *, result: RagKnowledgeSearchResult) -> None:
        self.result = result
        self.requests = []

    async def search(self, request):
        self.requests.append(request)
        return self.result


def _search_result(
        *,
        direct_evidence: tuple[RagDirectEvidence, ...],
        graph_evidence: tuple[RagGraphEvidence, ...],
) -> RagKnowledgeSearchResult:
    warning = RagAnswerabilityWarning(
        warnings=(RagAnswerabilityWarningReason.PARTIAL_COVERAGE,),
        guidance="回答时说明证据范围。",
    )
    graph_enhancement = RagGraphEnhancementResult(
        graph_evidence=graph_evidence,
        ontology_hints=(
            RagOntologyHint(
                concept="partial_coverage",
                path_preview=("direct_evidence", "graph_evidence"),
            ),
        ),
    )
    return RagKnowledgeSearchResult(
        hard_gate=RagHardGateDecision(status=RagHardGateStatus.PASSED),
        direct_evidence=direct_evidence,
        answerability_warning=warning,
        graph_enhancement=graph_enhancement,
        context=RagContextPackage(
            query="AppBuilder API Key 怎么申请？",
            direct_evidence=direct_evidence,
            context_text=(
                "<rag_context>"
                "<direct_evidence>"
                "<evidence citation_id=\"E1\">请求必须携带 AppBuilder API Key。</evidence>"
                "</direct_evidence>"
                "</rag_context>"
            ),
            answerability_warning=warning,
            graph_evidence=graph_evidence,
            ontology_hints=graph_enhancement.ontology_hints,
        ),
    )
