from __future__ import annotations

from chat.application.rag.answerability.models import (
    RagAnswerabilityInput,
    RagHardGateDecision,
    RagHardGateReason,
    RagHardGateStatus,
)

# 硬门控的绝对分数下限。低于该值意味着即使排名第一的候选也几乎不可信，
# 直接拒答可以避免把噪声证据交给主模型。
ABSOLUTE_MIN_SCORE_THRESHOLD = 0.3


class AnswerabilityHardGate:
    """只处理极端确定失败的硬门控。

    硬门控只拦截两类明显不可答的情况：空召回、Top-K 全部低于绝对分数下限。
    它不尝试做细粒度的证据质量评估，那是 Soft Gate 的职责。
    """

    __slots__ = ("_absolute_min_score_threshold",)

    def __init__(
            self,
            *,
            absolute_min_score_threshold: float = ABSOLUTE_MIN_SCORE_THRESHOLD,
    ) -> None:
        self._absolute_min_score_threshold = absolute_min_score_threshold

    def decide(self, answerability_input: RagAnswerabilityInput) -> RagHardGateDecision:
        # 空召回：没有任何候选可以支持回答，直接拒答。
        if not answerability_input.ranked:
            return RagHardGateDecision(
                status=RagHardGateStatus.REJECTED,
                reason=RagHardGateReason.EMPTY_RETRIEVAL,
            )

        # 候选已按分数排序；最高分都低于绝对下限时，证据整体不可信。
        if answerability_input.ranked[0].score < self._absolute_min_score_threshold:
            return RagHardGateDecision(
                status=RagHardGateStatus.REJECTED,
                reason=RagHardGateReason.TOPK_ALL_BELOW_ABSOLUTE_MIN_SCORE,
            )

        return RagHardGateDecision(status=RagHardGateStatus.PASSED)

    def accepts(self, score: float) -> bool:
        return score >= self._absolute_min_score_threshold
