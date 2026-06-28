from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from chat.application.utils.ranking_engine.models import ScoreSignal


class RagRetrievalProfile(StrEnum):
    """主模型可选择的 RAG 检索意图。"""

    BALANCED = "balanced"
    SEMANTIC = "semantic"
    LEXICAL = "lexical"
    ANCHORED_EXACT = "anchored_exact"


@dataclass(frozen=True, slots=True)
class ScoredChunk:
    """已经完成检索和原始打分的 child chunk 候选。"""

    chunk_id: str  # child chunk id
    text: str  # 供 reranker 和多样性控制读取的证据文本
    score_signal: ScoreSignal  # 上游检索通道已经产出的原始分数信号
