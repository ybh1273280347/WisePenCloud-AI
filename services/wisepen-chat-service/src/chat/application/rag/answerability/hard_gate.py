from __future__ import annotations

from chat.application.rag.answerability.models import (
    RagAnswerabilityInput,
    RagHardGateDecision,
    RagHardGateReason,
    RagHardGateStatus,
)


ABSOLUTE_MIN_SCORE_THRESHOLD = 0.3


class AnswerabilityHardGate:
    """只处理极端确定失败的硬门控。"""

    __slots__ = ("_absolute_min_score_threshold",)

    def __init__(
        self,
        *,
        absolute_min_score_threshold: float = ABSOLUTE_MIN_SCORE_THRESHOLD,
    ) -> None:
        self._absolute_min_score_threshold = absolute_min_score_threshold

    def decide(self, answerability_input: RagAnswerabilityInput) -> RagHardGateDecision:
        if not answerability_input.ranked:
            return RagHardGateDecision(
                status=RagHardGateStatus.REJECTED,
                reason=RagHardGateReason.EMPTY_RETRIEVAL,
            )

        if all(
            item.score < self._absolute_min_score_threshold
            for item in answerability_input.ranked
        ):
            return RagHardGateDecision(
                status=RagHardGateStatus.REJECTED,
                reason=RagHardGateReason.TOPK_ALL_BELOW_ABSOLUTE_MIN_SCORE,
            )

        return RagHardGateDecision(status=RagHardGateStatus.PASSED)
