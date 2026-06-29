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
    """Answerability Gate 的输入。"""

    query: str  # 用户原始问题
    retrieval_profile: str  # 当前检索模式，便于小模型判断证据风险
    ranked: tuple[RankedCandidate, ...]  # ranking 后保留下来的 direct topK evidence


@dataclass(frozen=True, slots=True)
class RagHardGateDecision:
    """Answerability Hard Gate 输出。"""

    status: RagHardGateStatus
    reason: RagHardGateReason | None = None

    @property
    def should_continue(self) -> bool:
        return self.status == RagHardGateStatus.PASSED


@dataclass(frozen=True, slots=True)
class RagAnswerabilityWarning:
    """Soft Gate 输出给 Context Builder / 主模型的风险提示。"""

    answerability_level: RagAnswerabilityLevel
    warnings: tuple[RagAnswerabilityWarningReason, ...] = ()
    guidance: str = ""

    @property
    def should_enhance_with_neo4j(self) -> bool:
        return bool(self.warnings)


@dataclass(frozen=True, slots=True)
class RagAnswerabilityDecision:
    """Answerability Gate 总输出。"""

    hard_gate: RagHardGateDecision
    supporting_citation_ids: tuple[str, ...] = ()
    answerability_warning: RagAnswerabilityWarning | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def should_continue(self) -> bool:
        return self.hard_gate.should_continue

    @property
    def should_enhance_with_neo4j(self) -> bool:
        return bool(
            self.answerability_warning
            and self.answerability_warning.should_enhance_with_neo4j
        )
