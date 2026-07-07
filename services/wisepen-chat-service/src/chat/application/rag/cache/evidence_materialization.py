from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RagEvidenceMaterializationCacheScope:
    """RAG evidence 物化缓存作用域。

    缓存只在权限和会话都确定时使用；不确定时调用方应直接跳过缓存。
    """

    user_id: str
    session_id: str
    resource_id: str
    permission_scope_key: str


@dataclass(frozen=True, slots=True)
class RagMaterializedEvidenceView:
    """不含本次排序 rank/score 的已授权 evidence 物化结果。"""

    parent_chunk_id: str
    document_version: str
    text: str
    citation_anchor: str
    page_label: str | None = None
    section_path: tuple[str, ...] = ()
    anchor_labels: tuple[str, ...] = ()
    matched_child_ids: tuple[str, ...] = ()


class RagEvidenceMaterializationCache(Protocol):
    async def get_many(
            self,
            *,
            scope: RagEvidenceMaterializationCacheScope,
            child_chunk_ids: tuple[str, ...],
    ) -> dict[str, RagMaterializedEvidenceView]:
        ...

    async def set_many(
            self,
            *,
            scope: RagEvidenceMaterializationCacheScope,
            views_by_child_id: dict[str, RagMaterializedEvidenceView],
    ) -> None:
        ...
