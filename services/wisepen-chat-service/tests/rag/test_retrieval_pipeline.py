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

scorers_package = types.ModuleType("chat.application.utils.ranking_engine.scorers")
scorers_package.__path__ = [str(ranking_engine_path / "scorers")]
sys.modules["chat.application.utils.ranking_engine.scorers"] = scorers_package

registry_module = types.ModuleType("chat.application.utils.ranking_engine.registry")
registry_module.get_ranking_engine = lambda name: None
sys.modules["chat.application.utils.ranking_engine.registry"] = registry_module


class _Settings:
    ZERO_ENTROPY_API_KEY = "test-zero-entropy-key"
    EVIDENCE_RANKER_ZE_MODEL = "test-rerank-model"
    EVIDENCE_RANKER_ZE_TOP_N = 20
    QUERY_MODEL = "test-query-model"


config_module = types.ModuleType("chat.core.config.app_settings")
config_module.settings = _Settings()
sys.modules["chat.core.config.app_settings"] = config_module

from chat.application.rag.answerability import (  # noqa: E402
    AnswerabilityHardGate,
    AnswerabilitySoftGate,
    AnswerabilitySoftGateError,
    RagAnswerabilityInput,
    RagAnswerabilityLevel,
    RagAnswerabilityWarningReason,
    RagHardGateReason,
)
from chat.application.rag.ranking import (  # noqa: E402
    RagEvidenceRankingRequest,
    RagEvidenceRankingService,
)
from chat.application.rag.retrieval import (  # noqa: E402
    RagRetrievalProfile,
    ScoredChunk,
)
from chat.application.rag.ingestion import (  # noqa: E402
    RagChildChunk,
    RagChunkingService,
    RagMarkdownIngestionPayload,
    RagParentChunk,
)
from chat.application.utils.chunking_engine.models import IndexKind  # noqa: E402
from chat.application.utils.ranking_engine.models import (  # noqa: E402
    RankCandidate,
    RankedCandidate,
)
from chat.application.utils.ranking_engine.engine import RankingEngine  # noqa: E402
from chat.application.utils.ranking_engine.pipeline import RankingPipeline  # noqa: E402


def _ranking_engine_without_reranker() -> RankingEngine:
    return RankingEngine(
        pipeline=RankingPipeline(
            name="test.rag.knowledge_search",
        )
    )


def test_chunking_service_produces_parent_and_child_chunks() -> None:
    page_one = "请求必须携带 AppBuilder API Key。 " * 120
    page_two = "POST /v2/ai_search/web_search 使用 Bearer token。 " * 120
    payload = RagMarkdownIngestionPayload(
        resource_id="resource-auth",
        document_id="doc-auth",
        document_version="v1",
        title="API 文档",
        markdown="\n\n".join(
            [
                "<!-- page 1 -->",
                "# 鉴权",
                page_one,
                "<!-- page 2 -->",
                "## 接口",
                page_two,
            ]
        ),
    )

    result = RagChunkingService().chunk_payload(payload)

    assert result.resource_id == "resource-auth"
    assert result.document_id == "doc-auth"
    assert result.document_version == "v1"
    assert result.pipeline == "parent_child_markdown"
    assert result.parent_chunks
    assert result.child_chunks
    assert all(isinstance(chunk, RagParentChunk) for chunk in result.parent_chunks)
    assert all(isinstance(chunk, RagChildChunk) for chunk in result.child_chunks)
    assert all(chunk.parent_chunk_id for chunk in result.child_chunks)


def test_chunking_service_persists_extra_indexes_for_evidence_location() -> None:
    markdown = "\n\n".join(
        [
            "<!-- page 1 -->",
            "# 鉴权",
            "请求必须携带 AppBuilder API Key。 " * 120,
            "<!-- page 2 -->",
            "## 接口",
            "POST /v2/ai_search/web_search 使用 Bearer token。 " * 120,
        ]
    )

    result = RagChunkingService().chunk(
        markdown=markdown,
        document_id="doc-auth",
        title="API 文档",
    )

    all_extra_indexes = tuple(
        extra_index
        for chunk in (*result.parent_chunks, *result.child_chunks)
        for extra_index in chunk.extra_indexes
    )
    assert all_extra_indexes
    assert {index.index_name for index in all_extra_indexes} >= {"page:1", "page:2"}

    page_one = next(index for index in all_extra_indexes if index.index_name == "page:1")
    page_two = next(index for index in all_extra_indexes if index.index_name == "page:2")
    assert page_one.index_kind == IndexKind.PAGE
    assert page_two.index_kind == IndexKind.PAGE
    assert page_one.start_offset == 0
    assert page_one.end_offset is not None
    assert page_two.start_offset == page_one.end_offset

    page_one_chunks = [
        chunk
        for chunk in result.child_chunks
        if any(extra_index.index_name == "page:1" for extra_index in chunk.extra_indexes)
    ]
    assert page_one_chunks
    assert all(chunk.page_label == "1" for chunk in page_one_chunks)
    assert all(chunk.start_offset is not None for chunk in page_one_chunks)
    assert all(chunk.end_offset is not None for chunk in page_one_chunks)


@pytest.mark.anyio
async def test_qdrant_rrf_order_is_passed_to_rerank_stage_without_fusion() -> None:
    service = RagEvidenceRankingService(
        ranking_engine=_ranking_engine_without_reranker()
    )

    ranking_result = await service.rank(
        RagEvidenceRankingRequest(
            query="AppBuilder API Key 鉴权",
            chunks=(
                _retrieved_hit(
                    chunk_id="chunk-a",
                    text="AppBuilder API Key 用于接口鉴权。",
                    retrieval_score=0.71,
                    retrieval_rank=1,
                ),
                _retrieved_hit(
                    chunk_id="chunk-b",
                    text="另一个接口说明 Bearer token。",
                    retrieval_score=0.69,
                    retrieval_rank=2,
                ),
                _retrieved_hit(
                    chunk_id="chunk-a",
                    text="AppBuilder API Key 用于接口鉴权。",
                    retrieval_score=0.64,
                    retrieval_rank=3,
                ),
            ),
            top_k=2,
        )
    )

    assert [item.candidate_id for item in ranking_result.ranked] == ["chunk-a", "chunk-b"]
    assert [item.candidate.prior_rank for item in ranking_result.ranked] == [1, 2]
    assert ranking_result.ranked[0].candidate.metadata == {"retrieval_score": 0.71}
    assert all(not item.signals for item in ranking_result.ranked)


def test_hard_gate_rejects_empty_retrieval() -> None:
    decision = AnswerabilityHardGate().decide(
        RagAnswerabilityInput(
            query="AppBuilder API Key 鉴权",
            retrieval_profile=RagRetrievalProfile.BALANCED.value,
            ranked=(),
        )
    )

    assert not decision.should_continue
    assert decision.reason == RagHardGateReason.EMPTY_RETRIEVAL


def test_hard_gate_rejects_when_all_topk_scores_are_extremely_low() -> None:
    decision = AnswerabilityHardGate().decide(
        RagAnswerabilityInput(
            query="AppBuilder API Key 鉴权",
            retrieval_profile=RagRetrievalProfile.BALANCED.value,
            ranked=(
                RankedCandidate(
                    candidate=RankCandidate(
                        candidate_id="chunk-low",
                        text="AppBuilder API Key 用于接口鉴权。",
                    ),
                    rank=1,
                    score=0.01,
                ),
            ),
        )
    )

    assert not decision.should_continue
    assert decision.reason == RagHardGateReason.TOPK_ALL_BELOW_ABSOLUTE_MIN_SCORE


@pytest.mark.anyio
async def test_soft_gate_returns_warning_and_triggers_graph_enhancement() -> None:
    warning = await AnswerabilitySoftGate(client=_SoftGateClient()).evaluate(
        RagAnswerabilityInput(
            query="AppBuilder API Key 鉴权覆盖哪些接口？",
            retrieval_profile=RagRetrievalProfile.BALANCED.value,
            ranked=(
                RankedCandidate(
                    candidate=RankCandidate(
                        candidate_id="chunk-partial",
                        text="AppBuilder API Key 用于部分接口鉴权。",
                    ),
                    rank=1,
                    score=0.42,
                ),
            ),
        )
    )

    assert warning.answerability_level == RagAnswerabilityLevel.PARTIAL
    assert warning.warnings == (RagAnswerabilityWarningReason.PARTIAL_COVERAGE,)
    assert warning.should_enhance_with_neo4j


@pytest.mark.anyio
async def test_soft_gate_rejects_inconsistent_level_and_warning_severity() -> None:
    service = AnswerabilitySoftGate(client=_SoftGateClient(
        content=(
            '{"answerability_level":"partial",'
            '"warnings":["ENTITY_AMBIGUOUS"],'
            '"guidance":"请先澄清实体。"}'
        )
    ))

    with pytest.raises(AnswerabilitySoftGateError):
        await service.evaluate(
            RagAnswerabilityInput(
                query="这里的 Apple 指哪个公司？",
                retrieval_profile=RagRetrievalProfile.BALANCED.value,
                ranked=(
                    RankedCandidate(
                        candidate=RankCandidate(
                            candidate_id="chunk-ambiguous",
                            text="Apple 在不同上下文中可能指公司或水果。",
                        ),
                        rank=1,
                        score=0.51,
                    ),
                ),
            )
        )


def _retrieved_hit(
    *,
    chunk_id: str,
    text: str,
    retrieval_score: float,
    retrieval_rank: int,
) -> ScoredChunk:
    return ScoredChunk(
        chunk_id=chunk_id,
        text=text,
        retrieval_score=retrieval_score,
        retrieval_rank=retrieval_rank,
    )


class _SoftGateClient:
    def __init__(self, *, content: str | None = None) -> None:
        self._content = content or (
            '{"answerability_level":"partial",'
            '"warnings":["PARTIAL_COVERAGE"],'
            '"guidance":"当前证据只覆盖部分接口，回答时说明范围限制。"}'
        )

    async def aquery(self, *args, **kwargs):
        return _SoftGateResponse(
            content=self._content
        )


class _SoftGateResponse:
    def __init__(self, *, content: str) -> None:
        self.content = content
        self.usage_tokens = 12
