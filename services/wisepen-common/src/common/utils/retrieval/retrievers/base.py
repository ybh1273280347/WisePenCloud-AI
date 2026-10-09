from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..fusion.base import Fusion


@dataclass(frozen=True, slots=True)
class Candidate:
    """检索阶段传递的候选；rank 保持来源顺序，score 保存当前阶段分数。"""

    candidate_id: str
    text: str
    rank: int
    score: float = 0.0
    vector: list[float] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)


class Retriever:
    """可插拔召回实现；业务方覆盖 retrieve 即可接入任意数据源。"""

    name = "default"

    def __init__(self, *, top_k: int = 30) -> None:
        if top_k <= 0:
            raise ValueError("retriever top_k must be positive")
        self.top_k = top_k

    async def retrieve(self, query: str) -> list[Candidate]:
        return []


class FusionRetriever(Retriever):
    """递归组合多个 Retriever，并把融合预算封装在检索组件内部。"""

    name = "fusion"

    def __init__(
        self,
        *,
        retrievers: list[Retriever],
        fusion: Fusion,
        top_k: int = 60,
    ) -> None:
        super().__init__(top_k=top_k)
        self.retrievers = retrievers
        self.fusion = fusion

    async def retrieve(self, query: str) -> list[Candidate]:
        result_sets = await asyncio.gather(
            *(
                retriever.retrieve(query=query)
                for retriever in self.retrievers
            )
        )
        return self.fusion.fuse(result_sets=result_sets)[:self.top_k]
