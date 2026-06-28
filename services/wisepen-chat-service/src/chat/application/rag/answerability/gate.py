from __future__ import annotations

from chat.application.rag.answerability.models import (
    RagAnswerabilityDecision,
    RagAnswerabilityInput,
    RagAnswerabilityStatus,
    RagRefusalReason,
)


LOW_RERANK_SCORE_THRESHOLD = 0.25


class AnswerabilityGate:
    """第一版确定性可回答性门控。"""

    __slots__ = ()

    def decide(self, answerability_input: RagAnswerabilityInput) -> RagAnswerabilityDecision:
        if not answerability_input.query.strip():
            return RagAnswerabilityDecision(
                status=RagAnswerabilityStatus.NEEDS_CLARIFICATION,
                refusal_reason=RagRefusalReason.EMPTY_QUERY,
            )

        if not answerability_input.ranked:
            return RagAnswerabilityDecision(
                status=RagAnswerabilityStatus.INSUFFICIENT_EVIDENCE,
                refusal_reason=RagRefusalReason.INSUFFICIENT_EVIDENCE,
            )

        top_candidate = answerability_input.ranked[0]
        if top_candidate.score < LOW_RERANK_SCORE_THRESHOLD:
            return RagAnswerabilityDecision(
                status=RagAnswerabilityStatus.INSUFFICIENT_EVIDENCE,
                refusal_reason=RagRefusalReason.LOW_RERANK_SCORE,
            )

        return RagAnswerabilityDecision(
            status=RagAnswerabilityStatus.ANSWERABLE,
            supporting_citation_ids=tuple(item.candidate_id for item in answerability_input.ranked),
            metadata={
                "retrieval_profile": answerability_input.retrieval_profile,
                "evidence_count": len(answerability_input.ranked),
            },
        )
