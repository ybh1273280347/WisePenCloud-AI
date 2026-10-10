from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..retrievers.base import Candidate


class Reranker:
    """精排基类；默认保留候选顺序和分数。"""

    name = "base"

    async def rerank(
        self,
        focus: str,
        candidates: list[Candidate],
    ) -> list[Candidate]:
        del focus
        return candidates
