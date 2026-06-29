from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from chat.application.rag.retrieval.models import ScoredChunk
from chat.application.utils.ranking_engine.engine import RankingEngine
from chat.application.utils.ranking_engine.models import (
    RankCandidate,
    RankQuery,
    RankedCandidate,
    RankRequest,
)
from chat.application.utils.ranking_engine.registry import get_ranking_engine
from chat.application.utils.ranking_engine.scorers.raw_score_signal_scorer import (
    RAW_SCORE_SIGNALS_METADATA_KEY,
)


@dataclass(frozen=True, slots=True)
class RagEvidenceRankingRequest:
    """已检索候选进入 evidence ranking 的输入。"""

    query: str  # 用户原始问题
    chunks: tuple[ScoredChunk, ...] = ()  # 已完成检索和打分的候选
    top_k: int = 20  # 最终返回上限
    candidate_limit: int = 100  # rerank/diversify 前的中间窗口


@dataclass(frozen=True, slots=True)
class RagEvidenceRankingResult:
    """RAG evidence ranking 输出。"""

    ranked: tuple[RankedCandidate, ...]  # 最终排序后的证据候选
    total_candidates: int  # 排序前候选总数


class RagEvidenceRankingService:
    """对已检索候选做 ranking engine 后处理。"""

    __slots__ = ("_ranking_engine",)

    def __init__(
        self,
        *,
        ranking_engine: RankingEngine | None = None,
    ) -> None:
        self._ranking_engine = ranking_engine or get_ranking_engine("rag.knowledge_search")

    async def rank(self, request: RagEvidenceRankingRequest) -> RagEvidenceRankingResult:
        candidates = self._build_rank_candidates(request.chunks)
        rank_result = await self._ranking_engine.rank_async(
            RankRequest(
                query=RankQuery(text=request.query),
                candidates=candidates,
                top_k=request.top_k,
                candidate_limit=request.candidate_limit,
            )
        )

        return RagEvidenceRankingResult(
            ranked=rank_result.ranked,
            total_candidates=rank_result.total_candidates,
        )

    @staticmethod
    def _build_rank_candidates(
        chunks: tuple[ScoredChunk, ...],
    ) -> tuple[RankCandidate, ...]:
        signals_by_chunk_id = defaultdict(list)
        text_by_chunk_id: dict[str, str] = {}
        for chunk in chunks:
            signals_by_chunk_id[chunk.chunk_id].append(chunk.score_signal)
            text_by_chunk_id.setdefault(chunk.chunk_id, chunk.text)

        return tuple(
            RankCandidate(
                candidate_id=chunk_id,
                text=text_by_chunk_id[chunk_id],
                metadata={RAW_SCORE_SIGNALS_METADATA_KEY: tuple(signals)},
            )
            for chunk_id, signals in signals_by_chunk_id.items()
        )
