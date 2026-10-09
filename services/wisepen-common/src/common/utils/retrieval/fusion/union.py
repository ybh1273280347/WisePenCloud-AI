from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from .base import Fusion

if TYPE_CHECKING:
    from ..retrievers.base import Candidate


class UnionFusion(Fusion):
    """按各路候选 rank 交替取值，并按 ID 稳定去重。"""

    name = "union"

    def fuse(
        self,
        result_sets: list[list[Candidate]],
    ) -> list[Candidate]:
        # 各路结果集按 rank 升序排列
        ordered_sets = [
            sorted(result_set, key=lambda candidate: candidate.rank)
            for result_set in result_sets
        ]

        merged: dict[str, Candidate] = {}  # 按 ID 去重，保持首次出现顺序
        max_length = max((len(result_set) for result_set in ordered_sets), default=0)

        for index in range(max_length):  # 按位置交替遍历各路
            for result_set in ordered_sets:
                if index >= len(result_set):  # 该路已取完
                    continue

                candidate = result_set[index]
                merged.setdefault(candidate.candidate_id, candidate)  # 首次出现为准

        # 重写 rank 和 score 后返回
        return [
            replace(candidate, rank=rank, score=0.0)
            for rank, candidate in enumerate(merged.values(), start=1)
        ]
