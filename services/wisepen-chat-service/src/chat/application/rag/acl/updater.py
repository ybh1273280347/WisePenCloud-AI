from __future__ import annotations

from chat.application.rag.acl.core import RagAclProjectionSyncTarget, RagResourceAclProjection


class RagAclProjectionUpdater:
    """同步 RAG 权限投影到各检索后端。"""

    __slots__ = ("_targets",)

    def __init__(
            self,
            *,
            targets: list[RagAclProjectionSyncTarget] | tuple[RagAclProjectionSyncTarget, ...] | None = None,
    ) -> None:
        self._targets = tuple(targets or ())

    async def update_read_acl(self, projection: RagResourceAclProjection) -> None:
        for target in self._targets:
            await target.update_acl_projection(projection)
