from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Literal

import numpy as np

from .base import Diversity

if TYPE_CHECKING:
    from ..retrievers.base import Candidate


class MmrDiversity(Diversity):
    """使用候选向量余弦相似度执行 MMR，并将选择分数写回候选。"""

    name = "mmr"

    def diversify(
        self,
        candidates: list[Candidate],
        mode: Literal["off", "moderate", "high"],
    ) -> list[Candidate]:
        if mode == "off":  # 关闭多样性时直接返回
            return candidates
        if mode not in {"moderate", "high"}:  # 校验模式
            raise ValueError(f"unsupported diversity mode: {mode}")

        ranked = candidates
        if not ranked:  # 无候选可处理
            return ranked

        lambda_mult = 0.75 if mode == "moderate" else 0.5  # 相关性权重
        relevance = _normalized_scores(ranked)  # 归一化相关性
        selected: list[Candidate] = []
        selected_ids: set[str] = set()

        while len(selected) < len(ranked):
            best: Candidate | None = None
            best_value = float("-inf")

            for candidate in ranked:
                if candidate.candidate_id in selected_ids:  # 跳过已选
                    continue

                # 与已选候选的最大余弦相似度，作为冗余惩罚
                penalty = max(
                    (
                        _cosine_similarity(candidate.vector, previous.vector)
                        for previous in selected
                    ),
                    default=0.0,
                )

                # MMR 得分：相关性 - 冗余惩罚
                value = lambda_mult * relevance[candidate.candidate_id] - (
                    1 - lambda_mult
                ) * penalty

                if value > best_value:
                    best = replace(
                        candidate,
                        rank=len(selected) + 1,
                        score=value,
                        metadata={
                            **candidate.metadata,
                            "diversity": self.name,
                            "relevance_score": candidate.score,
                        },
                    )
                    best_value = value

            if best is None:  # 兜底退出
                break

            selected_ids.add(best.candidate_id)
            selected.append(best)

        return selected


def _normalized_scores(candidates: list[Candidate]) -> dict[str, float]:
    """将候选分数线性归一化到 [0, 1]。"""
    scores = [candidate.score for candidate in candidates]
    minimum = min(scores)
    maximum = max(scores)

    if maximum == minimum:  # 所有分数相同
        return {candidate.candidate_id: 1.0 for candidate in candidates}

    return {
        candidate.candidate_id: (candidate.score - minimum) / (maximum - minimum)
        for candidate in candidates
    }


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    """计算两个向量的余弦相似度，非法输入返回 0。"""
    if not left or not right or len(left) != len(right):
        return 0.0

    left_vector = np.asarray(left)
    right_vector = np.asarray(right)
    left_norm = np.linalg.norm(left_vector)
    right_norm = np.linalg.norm(right_vector)

    if left_norm == 0.0 or right_norm == 0.0:  # 零向量
        return 0.0

    return float(np.dot(left_vector, right_vector) / (left_norm * right_norm))