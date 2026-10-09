from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from ..retrievers.base import Candidate


class Diversity:
    """多样化基类；默认对所有模式原样传递候选。"""

    name = "default"

    def diversify(
        self,
        candidates: list[Candidate],
        mode: Literal["off", "moderate", "high"],
    ) -> list[Candidate]:
        del mode
        return candidates
