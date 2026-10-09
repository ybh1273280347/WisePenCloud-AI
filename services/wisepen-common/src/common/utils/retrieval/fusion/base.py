from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..retrievers.base import Candidate


class Fusion(ABC):
    """多路候选融合算法接口，不提供默认融合策略。"""

    name = "default"

    @abstractmethod
    def fuse(
        self,
        result_sets: list[list[Candidate]],
    ) -> list[Candidate]:
        raise NotImplementedError
