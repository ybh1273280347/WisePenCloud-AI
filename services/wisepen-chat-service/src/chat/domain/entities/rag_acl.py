from __future__ import annotations

from datetime import datetime, timezone

from beanie import Document
from pydantic import BaseModel, Field
from pymongo import ASCENDING, IndexModel


class RagComputedGroupAclProjectionDocument(BaseModel):
    group_id: str = Field(..., description="资源绑定小组 ID")
    is_readable: bool = Field(..., description="该小组基础 VIEW 权限")
    readable_users: list[str] = Field(default_factory=list, description="小组不可读时的用户白名单")
    excluded_read_users: list[str] = Field(default_factory=list, description="小组可读时的用户黑名单")


class RagAclProjectionDocument(Document):
    """RAG 侧资源权限投影。

    只保存检索前过滤需要的 VIEW/read 投影，不保存完整资源权限模型。
    """

    resource_id: str = Field(..., description="资源 ID")
    owner_id: str = Field(..., description="资源拥有者 ID")
    readable_users: list[str] = Field(default_factory=list, description="资源级 VIEW 指定用户")
    computed_group_acls: list[RagComputedGroupAclProjectionDocument] = Field(
        default_factory=list,
        description="小组 VIEW 权限投影",
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "wisepen_rag_acl_projections"
        locators = [
            IndexModel(
                [("resource_id", ASCENDING)],
                name="idx_rag_acl_projection_resource_id",
                unique=True,
            ),
        ]
