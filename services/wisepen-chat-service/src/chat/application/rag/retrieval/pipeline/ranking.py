from __future__ import annotations

from dataclasses import dataclass

from chat.application.rag.retrieval.models import (
    RagRetrievalChannel,
    RagRetrievalProfile,
    ScoredChunk,
)
from chat.application.utils.ranking_engine.engine import RankingEngine
from chat.application.utils.ranking_engine.models import (
    RankCandidate,
    RankQuery,
    RankedCandidate,
    RankRequest,
    ScoreSignal,
    ScoreSignalKind,
)
from chat.application.utils.ranking_engine.registry import get_ranking_engine


@dataclass(frozen=True, slots=True)
class RagEvidenceRankingRequest:
    """已检索候选进入 evidence ranking 的输入。"""

    query: str  # 用户原始问题
    chunks: tuple[ScoredChunk, ...] = ()  # 已完成上游融合排序的候选
    retrieval_profile: RagRetrievalProfile = RagRetrievalProfile.BALANCED
    top_k: int = 20  # 最终返回给 answerability gate 的上限
    candidate_limit: int = 100  # rerank/diversify 前的中间窗口，避免一次性喂给 ranking engine 过多候选


@dataclass(frozen=True, slots=True)
class RagEvidenceRankingResult:
    """RAG evidence ranking 输出。"""

    ranked: tuple[RankedCandidate, ...]  # 最终排序后的证据候选
    total_candidates: int  # 排序前候选总数


class RagEvidenceRankingService:
    """对已检索候选做 ranking engine 后处理。"""

    __slots__ = (
        "_lexical_dense_rrf_weight",
        "_lexical_sparse_rrf_weight",
        "_ranking_engine",
        "_semantic_dense_rrf_weight",
        "_semantic_sparse_rrf_weight",
    )

    def __init__(
            self,
            *,
            ranking_engine: RankingEngine | None = None,
            semantic_dense_rrf_weight: float = 2.0,
            semantic_sparse_rrf_weight: float = 0.75,
            lexical_dense_rrf_weight: float = 0.75,
            lexical_sparse_rrf_weight: float = 2.0,
    ) -> None:
        self._ranking_engine = ranking_engine or get_ranking_engine("rag.knowledge_search")
        self._semantic_dense_rrf_weight = semantic_dense_rrf_weight
        self._semantic_sparse_rrf_weight = semantic_sparse_rrf_weight
        self._lexical_dense_rrf_weight = lexical_dense_rrf_weight
        self._lexical_sparse_rrf_weight = lexical_sparse_rrf_weight

    async def rank(self, request: RagEvidenceRankingRequest) -> RagEvidenceRankingResult:
        candidates = self._build_rank_candidates(request.chunks)
        rank_result = await self._ranking_engine.rank_async(
            RankRequest(
                query=RankQuery(text=request.query),
                candidates=candidates,
                top_k=request.top_k,
                candidate_limit=request.candidate_limit,
                signals=self._build_retrieval_signals(request),
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

            candidates_by_chunk_id[chunk.chunk_id] = RankCandidate(
                candidate_id=chunk.chunk_id,
                text=chunk.text,
                prior_rank=chunk.retrieval_rank,
                group_key=chunk.group_key,
            )

        return tuple(candidates_by_chunk_id.values())

    def _build_retrieval_signals(
            self,
            request: RagEvidenceRankingRequest,
    ) -> tuple[ScoreSignal, ...]:
        weights = self._channel_weights(request.retrieval_profile)
        signals: list[ScoreSignal] = []
        seen_chunk_ids: set[str] = set()
        for chunk in request.chunks:
            if chunk.chunk_id in seen_chunk_ids:
                continue
            seen_chunk_ids.add(chunk.chunk_id)

            for signal in chunk.retrieval_signals:
                signals.append(
                    ScoreSignal(
                        candidate_id=chunk.chunk_id,
                        name=f"qdrant:{signal.channel.value}",
                        value=signal.score,
                        kind=(
                            ScoreSignalKind.VECTOR
                            if signal.channel == RagRetrievalChannel.DENSE
                            else ScoreSignalKind.LEXICAL
                        ),
                        rank=signal.rank,
                        weight=weights[signal.channel],
                        reason="Qdrant retrieval channel rank.",
                        metadata={"channel": signal.channel.value},
                    )
                )

        return tuple(signals)

    def _channel_weights(
            self,
            profile: RagRetrievalProfile,
    ) -> dict[RagRetrievalChannel, float]:
        if profile == RagRetrievalProfile.SEMANTIC:
            return {
                RagRetrievalChannel.DENSE: self._semantic_dense_rrf_weight,
                RagRetrievalChannel.SPARSE: self._semantic_sparse_rrf_weight,
            }
        if profile == RagRetrievalProfile.LEXICAL:
            return {
                RagRetrievalChannel.DENSE: self._lexical_dense_rrf_weight,
                RagRetrievalChannel.SPARSE: self._lexical_sparse_rrf_weight,
            }
        return {
            RagRetrievalChannel.DENSE: 1.0,
            RagRetrievalChannel.SPARSE: 1.0,
        }
