from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from chat.application.utils.ranking_engine.models import RankedCandidate


class RagHardGateStatus(StrEnum):
    """Answerability Hard Gate 状态。"""

    PASSED = "passed"
    REJECTED = "rejected"


class RagHardGateReason(StrEnum):
    """服务端硬拒答原因。"""

    EMPTY_RETRIEVAL = "empty_retrieval"
    TOPK_ALL_BELOW_ABSOLUTE_MIN_SCORE = "topk_all_below_absolute_min_score"


class RagAnswerabilityLevel(StrEnum):
    """Soft Gate 给主模型的证据质量等级。"""

    GOOD = "good"
    PARTIAL = "partial"
    RISKY = "risky"
    POOR = "poor"


class RagAnswerabilityWarningReason(StrEnum):
    """Soft Gate 风险原因。"""

    LOW_DIRECTNESS = "low_directness"
    PARTIAL_COVERAGE = "partial_coverage"
    ENTITY_AMBIGUOUS = "entity_ambiguous"
    CONTEXT_MISMATCH = "context_mismatch"
    EVIDENCE_CONFLICT = "evidence_conflict"


@dataclass(frozen=True, slots=True)
class RagAnswerabilityInput:
    """Answerability Gate 的输入。

    这里只接收 ranking 之后的候选，而不是原始检索结果，保证软硬门控都在同一套
    evidence 集合上做判断，避免标准不一致。
    """

    query: str  # 用户原始问题
    retrieval_profile: str  # 当前检索模式，便于小模型判断证据风险
    ranked: tuple[RankedCandidate, ...]  # ranking 后保留下来的 direct topK evidence


@dataclass(frozen=True, slots=True)
class RagHardGateDecision:
    """Answerability Hard Gate 输出。"""

    status: RagHardGateStatus
    reason: RagHardGateReason | None = None  # 仅在被拒时才有意义，通过时无需解释

    @property
    def should_continue(self) -> bool:
        return self.status == RagHardGateStatus.PASSED


@dataclass(frozen=True, slots=True)
class RagAnswerabilityWarning:
    """Soft Gate 输出给 Context Builder / 主模型的风险提示。"""

    answerability_level: RagAnswerabilityLevel
    warnings: tuple[RagAnswerabilityWarningReason, ...] = ()
    guidance: str = ""  # 面向主模型的具体回答策略说明

    @property
    def should_enhance_with_neo4j(self) -> bool:
        """只要存在 warning，就触发 Neo4j Ontology Enhancement 做进一步图增强。"""
        return bool(self.warnings)


@dataclass(frozen=True, slots=True)
class RagAnswerabilityDecision:
    """Answerability Gate 总输出。"""

    hard_gate: RagHardGateDecision
    # 当 hard_gate 通过时，这些引用 id 将用于构建带引用的最终回答。
    supporting_citation_ids: tuple[str, ...] = ()
    answerability_warning: RagAnswerabilityWarning | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def should_continue(self) -> bool:
        return self.hard_gate.should_continue

    @property
    def should_enhance_with_neo4j(self) -> bool:
        """只有先通过硬门控，且软门控报出 warning 时，才值得做图增强。"""
        return bool(
            self.should_continue
            and self.answerability_warning
            and self.answerability_warning.should_enhance_with_neo4j
        )
