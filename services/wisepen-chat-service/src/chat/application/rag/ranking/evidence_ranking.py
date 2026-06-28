from __future__ import annotations

from collections import defaultdict

from chat.application.rag.ranking.models import (
    RagEvidenceRankingRequest,
    RagEvidenceRankingResult,
)
from chat.application.rag.retrieval.models import ScoredChunk
from chat.application.utils.ranking_engine.engine import RankingEngine
from chat.application.utils.ranking_engine.models import (
    RankCandidate,
    RankQuery,
    RankRequest,
)
from chat.application.utils.ranking_engine.registry import get_ranking_engine
from chat.application.utils.ranking_engine.scorers.raw_score_signal_scorer import (
    RAW_SCORE_SIGNALS_METADATA_KEY,
)


class RagEvidenceRankingService:
    """对已检索候选做 ranking engine 后处理。"""

    __slots__ = ("_ranking_engine",)

    def __init__(
        self,
        *,
        ranking_engine: RankingEngine | None = None,
    ) -> None:
        if ranking_engine is None:
            ranking_engine = get_ranking_engine("rag.knowledge_search")

        self._ranking_engine = ranking_engine

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
