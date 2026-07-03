from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RagRetrievalProfile(StrEnum):
    """主模型可选择的 RAG 检索意图。

    这些 profile 会决定检索时语义和 lexical 的权重分配，以及是否启用锚点精确匹配。
    """

    BALANCED = "balanced"  # 语义 + lexical 均衡
    SEMANTIC = "semantic"  # 偏重向量语义相似度
    LEXICAL = "lexical"  # 偏重关键词匹配
    ANCHORED_EXACT = "anchored_exact"  # 锚点或标题精确匹配，用于定位到具体段落


@dataclass(frozen=True, slots=True)
class ScoredChunk:
    """已经由上游检索层完成融合排序的 child chunk 候选。"""

    chunk_id: str  # child chunk id
    text: str  # 供 reranker 和多样性控制读取的证据文本
    retrieval_score: float | None = None  # 上游检索层返回的融合后分数；None 表示来源未提供分数
    retrieval_rank: int | None = None  # 上游检索层返回的原始排名，从 1 开始
    group_key: str | None = None  # 多样性控制分组键，例如同文档或同父 chunk
