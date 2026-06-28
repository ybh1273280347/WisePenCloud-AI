from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from chat.application.utils.ranking_engine.models import RankedCandidate


class RagAnswerabilityStatus(StrEnum):
    """RAG 可回答性状态。"""

    ANSWERABLE = "answerable"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    NEEDS_CLARIFICATION = "needs_clarification"


class RagRefusalReason(StrEnum):
    """模型可读拒答原因。"""

    EMPTY_QUERY = "empty_query"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    LOW_RERANK_SCORE = "low_rerank_score"


@dataclass(frozen=True, slots=True)
class RagAnswerabilityInput:
    """Answerability Gate 的确定性输入。"""

    query: str  # 用户原始问题
    retrieval_profile: str  # 当前检索模式，便于后续扩展差异化门控
    ranked: tuple[RankedCandidate, ...]  # retrieval 后保留下来的证据候选


@dataclass(frozen=True, slots=True)
class RagAnswerabilityDecision:
    """Answerability Gate 输出。"""

    status: RagAnswerabilityStatus  # 当前可回答性结论
    supporting_citation_ids: tuple[str, ...] = ()  # 支撑回答的 citation id
    refusal_reason: RagRefusalReason | None = None  # 机器可读拒答原因
    metadata: dict[str, object] = field(default_factory=dict)  # 额外策略上下文
