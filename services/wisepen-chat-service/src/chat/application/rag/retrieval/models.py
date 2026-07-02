from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

class RagRetrievalProfile(StrEnum):
    """主模型可选择的 RAG 检索意图。"""

    BALANCED = "balanced"
    SEMANTIC = "semantic"
    LEXICAL = "lexical"
    ANCHORED_EXACT = "anchored_exact"


@dataclass(frozen=True, slots=True)
class ScoredChunk:
    """已经由上游检索层完成融合排序的 child chunk 候选。"""

    chunk_id: str  # child chunk id
    text: str  # 供 reranker 和多样性控制读取的证据文本
    retrieval_score: float | None = None  # Qdrant 等上游检索层返回的融合后分数
    retrieval_rank: int | None = None  # 上游检索层返回的原始排名，从 1 开始
    group_key: str | None = None  # 多样性控制分组键，例如同文档或同父 chunk
