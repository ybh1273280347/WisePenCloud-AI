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


config_module = types.ModuleType("chat.core.config.app_settings")
config_module.settings = _Settings()
sys.modules["chat.core.config.app_settings"] = config_module

from chat.application.rag.answerability import AnswerabilityGate, RagAnswerabilityInput, RagRefusalReason
from chat.application.rag.ranking import (
    RagEvidenceRankingRequest,
    RagEvidenceRankingService,
)
from chat.application.rag.retrieval import (
    RagRetrievalProfile,
    ScoredChunk,
)
from chat.application.rag.ingestion import (
    RagChildChunk,
    RagChunkingService,
    RagParentChunk,
)
from chat.application.utils.ranking_engine.models import (
    RankCandidate,
    RankedCandidate,
    ScoreSignal,
    ScoreSignalKind,
)
from chat.application.utils.ranking_engine.engine import RankingEngine
from chat.application.utils.ranking_engine.fusion import WeightedRrfFusion
from chat.application.utils.ranking_engine.pipeline import RankingPipeline
from chat.application.utils.ranking_engine.scorers.raw_score_signal_scorer import (
    RawScoreSignalScorer,
)


def _ranking_engine_without_reranker() -> RankingEngine:
    return RankingEngine(
        pipeline=RankingPipeline(
            name="test.rag.knowledge_search",
            scorers=(RawScoreSignalScorer(),),
            fusion=WeightedRrfFusion(),
        )
    )


def test_chunking_service_produces_parent_and_child_chunks() -> None:
    markdown = "\n\n".join(
        [
            "# 鉴权",
            "请求必须携带 AppBuilder API Key。 " * 60,
            "## 接口",
            "POST /v2/ai_search/web_search 使用 Bearer token。 " * 60,
        ]
    )

    result = RagChunkingService().chunk(
        markdown=markdown,
        document_id="doc-auth",
        title="API 文档",
    )

    assert result.pipeline == "nested_markdown"
    assert result.parent_chunks
    assert result.child_chunks
    assert all(isinstance(chunk, RagParentChunk) for chunk in result.parent_chunks)
    assert all(isinstance(chunk, RagChildChunk) for chunk in result.child_chunks)
    assert all(chunk.parent_chunk_id for chunk in result.child_chunks)


@pytest.mark.anyio
async def test_dense_and_sparse_scores_are_fused_by_ranking_engine() -> None:
    service = RagEvidenceRankingService(
        ranking_engine=_ranking_engine_without_reranker()
    )

    ranking_result = await service.rank(
        RagEvidenceRankingRequest(
            query="AppBuilder API Key 鉴权",
            chunks=(
                _scored_hit(
                    chunk_id="chunk-a",
                    text="AppBuilder API Key 用于接口鉴权。",
                    name="retrieval.dense",
                    kind=ScoreSignalKind.VECTOR,
                    score=0.92,
                    rank=1,
                ),
                _scored_hit(
                    chunk_id="chunk-b",
                    text="另一个接口说明 Bearer token。",
                    name="retrieval.dense",
                    kind=ScoreSignalKind.VECTOR,
                    score=0.89,
                    rank=2,
                ),
                _scored_hit(
                    chunk_id="chunk-b",
                    text="另一个接口说明 Bearer token。",
                    name="retrieval.sparse",
                    kind=ScoreSignalKind.LEXICAL,
                    score=11.4,
                    rank=1,
                ),
                _scored_hit(
                    chunk_id="chunk-a",
                    text="AppBuilder API Key 用于接口鉴权。",
                    name="retrieval.sparse",
                    kind=ScoreSignalKind.LEXICAL,
                    score=8.6,
                    rank=2,
                ),
            ),
            top_k=2,
        )
    )

    assert [item.candidate_id for item in ranking_result.ranked] == ["chunk-a", "chunk-b"]
    assert {signal.name for signal in ranking_result.ranked[0].signals} == {
        "retrieval.dense",
        "retrieval.sparse",
    }


def test_answerability_refuses_when_final_score_is_low() -> None:
    decision = AnswerabilityGate().decide(
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
                    score=0.12,
                ),
            ),
        )
    )

    assert decision.status == "insufficient_evidence"
    assert decision.refusal_reason == RagRefusalReason.LOW_RERANK_SCORE


def _scored_hit(
    *,
    chunk_id: str,
    text: str,
    name: str,
    kind: ScoreSignalKind,
    score: float,
    rank: int,
) -> ScoredChunk:
    return ScoredChunk(
        chunk_id=chunk_id,
        text=text,
        score_signal=ScoreSignal(
            candidate_id=chunk_id,
            name=name,
            value=score,
            kind=kind,
            rank=rank,
        ),
    )
