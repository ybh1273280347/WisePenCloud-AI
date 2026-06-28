from __future__ import annotations

from chat.application.utils.ranking_engine.models import (
    RankCandidate,
    RankQuery,
    ScoreSignal,
)


RAW_SCORE_SIGNALS_METADATA_KEY = "raw_score_signals"


class RawScoreSignalScorer:
    """读取上游检索系统已经产出的原始排序信号。"""

    __slots__ = ("name",)

    def __init__(self) -> None:
        self.name = "raw_score_signal_scorer"

    def score(
        self,
        *,
        query: RankQuery,
        candidates: tuple[RankCandidate, ...],
    ) -> tuple[ScoreSignal, ...]:
        signals: list[ScoreSignal] = []

        for candidate in candidates:
            # 此时上游应该已经完成原始打分，这里只读取显式传入的信号。
            raw_signals = candidate.metadata.get(RAW_SCORE_SIGNALS_METADATA_KEY, ())
            if not isinstance(raw_signals, tuple):
                continue

            for signal in raw_signals:
                # 防止业务 metadata 中混入其他候选的信号，避免 fusion 阶段串分。
                if not isinstance(signal, ScoreSignal):
                    continue
                if signal.candidate_id != candidate.candidate_id:
                    continue
                signals.append(signal)

        return tuple(signals)
