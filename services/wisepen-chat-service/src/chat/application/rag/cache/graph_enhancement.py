from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from chat.application.rag.graph import RagGraphEnhancementResult


@dataclass(frozen=True, slots=True)
class RagGraphEnhancementCacheKey:
    """Graph 后置增强缓存 key，不缓存最终回答。"""

    resource_id: str
    direct_evidence_signature: str
    warning_signature: str
    permission_scope_key: str
    graph_version: str
    ontology_schema_version: str


class RagGraphEnhancementCache(Protocol):
    async def get_graph_enhancement(
            self,
            key: RagGraphEnhancementCacheKey,
    ) -> RagGraphEnhancementResult | None:
        ...

    async def set_graph_enhancement(
            self,
            key: RagGraphEnhancementCacheKey,
            result: RagGraphEnhancementResult,
    ) -> None:
        ...
