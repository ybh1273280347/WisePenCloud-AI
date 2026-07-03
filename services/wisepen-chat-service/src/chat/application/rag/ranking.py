from __future__ import annotations

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


@dataclass(frozen=True, slots=True)
class RagEvidenceRankingRequest:
    """已检索候选进入 evidence ranking 的输入。"""

    query: str  # 用户原始问题
    chunks: tuple[ScoredChunk, ...] = ()  # 已完成上游融合排序的候选
    top_k: int = 20  # 最终返回给 answerability gate 的上限
    candidate_limit: int = 100  # rerank/diversify 前的中间窗口，避免一次性喂给 ranking engine 过多候选


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
        """把 ScoredChunk 去重后转成 RankingEngine 需要的 RankCandidate。

        上游不同检索源可能召回同一个 chunk，这里按 chunk_id 去重，保留第一次出现。
        """
        candidates_by_chunk_id: dict[str, RankCandidate] = {}
        for chunk in chunks:
            if chunk.chunk_id in candidates_by_chunk_id:
                continue

            metadata = {}
            if chunk.retrieval_score is not None:
                metadata["retrieval_score"] = chunk.retrieval_score

            candidates_by_chunk_id[chunk.chunk_id] = RankCandidate(
                candidate_id=chunk.chunk_id,
                text=chunk.text,
                prior_rank=chunk.retrieval_rank,
                group_key=chunk.group_key,
                metadata=metadata,
            )

        return tuple(candidates_by_chunk_id.values())
