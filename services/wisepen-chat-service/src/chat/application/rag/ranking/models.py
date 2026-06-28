from __future__ import annotations

from dataclasses import dataclass

from chat.application.rag.retrieval.models import ScoredChunk
from chat.application.utils.ranking_engine.models import RankedCandidate


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
