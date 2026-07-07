from __future__ import annotations

from typing import Protocol

from .models import RagResourceAclProjection


class RagAclProjectionRepository(Protocol):
    """RAG read ACL 投影的持久化协议。"""

    async def upsert_projection(self, projection: RagResourceAclProjection) -> None:
        """写入或更新资源权限投影。"""
        ...

    async def get_projection(self, resource_id: str) -> RagResourceAclProjection | None:
        """按 resource_id 查询已存储的权限投影。"""
        ...

    async def load_resource_projection(self, resource_id: str) -> RagResourceAclProjection | None:
        """从 resource-service 原始数据重新构建权限投影（回源查询）。"""
        ...


class RagAclProjectionSyncTarget(Protocol):
    """权限投影变更的下游同步目标。"""

    async def update_acl_projection(self, projection: RagResourceAclProjection) -> None:
        ...
