"""Mongo adapter：读取上游资源集合中的权威 ACL。"""

from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from pymongo.asynchronous.collection import AsyncCollection

from rag.domain.acl import GroupResourceAcl, ResourceAcl
from rag.domain.repositories.authoritative_acl_reader import AuthoritativeAclReader


class AuthoritativeAclError(ValueError):
    """上游资源 ACL 数据不满足 RAG 所需契约。"""


class MongoAuthoritativeAclReader(AuthoritativeAclReader):
    """只读上游 ``wisepen_resource_items``，不保存或读取本地 ACL。"""

    __slots__ = ("_collection",)

    def __init__(self, *, collection: AsyncCollection[dict[str, Any]]) -> None:
        self._collection = collection

    async def get_resource_acl(self, resource_id: str) -> ResourceAcl | None:
        if not ObjectId.is_valid(resource_id):
            raise AuthoritativeAclError("resource_id must be a valid ObjectId")

        record = await self._collection.find_one({"_id": ObjectId(resource_id)})
        if record is None:
            return None
        return _to_resource_acl(record, resource_id)


def _to_resource_acl(record: dict[str, Any], resource_id: str) -> ResourceAcl:
    owner_id = record.get("ownerId")
    if not isinstance(owner_id, str) or not owner_id.strip():
        raise AuthoritativeAclError("ownerId must be a non-empty string")

    update_time = record.get("updateTime")
    if not isinstance(update_time, datetime):
        raise AuthoritativeAclError("updateTime must be a datetime")
    if update_time.tzinfo is None:
        update_time = update_time.replace(tzinfo=UTC)

    user_access = _read_user_masks(record.get("specifiedUsersGrantedActionsMask"))
    return ResourceAcl(
        resource_id=resource_id,
        acl_revision=int(update_time.timestamp() * 1000),
        owner_id=owner_id.strip(),
        readable_users=user_access["readable_users"],
        excluded_read_users=user_access["excluded_read_users"],
        group_acls=_read_group_acls(record.get("computedGroupAcls")),
    )


def _read_user_masks(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {"readable_users": [], "excluded_read_users": []}
    readable_users: list[str] = []
    excluded_read_users: list[str] = []
    for user_id, mask in value.items():
        if not isinstance(user_id, str) or not user_id.strip():
            continue
        if isinstance(mask, bool) or not isinstance(mask, int):
            continue
        (readable_users if _has_view(mask) else excluded_read_users).append(
            user_id.strip()
        )
    return {
        "readable_users": readable_users,
        "excluded_read_users": excluded_read_users,
    }


def _read_group_acls(value: Any) -> list[GroupResourceAcl]:
    if not isinstance(value, dict):
        return []
    group_acls: list[GroupResourceAcl] = []
    for group_id, group_value in value.items():
        if not isinstance(group_id, str) or not group_id.strip():
            continue
        if not isinstance(group_value, dict):
            continue
        default_readable = _has_view(group_value.get("baseMask"))
        user_access = _read_user_masks(group_value.get("userMasks"))
        if default_readable:
            readable_users = []
            excluded_read_users = user_access["excluded_read_users"]
        else:
            readable_users = user_access["readable_users"]
            excluded_read_users = []
        group_acls.append(
            GroupResourceAcl(
                group_id=group_id.strip(),
                default_readable=default_readable,
                readable_users=readable_users,
                excluded_read_users=excluded_read_users,
            )
        )
    return group_acls


def _has_view(mask: Any) -> bool:
    return isinstance(mask, int) and not isinstance(mask, bool) and (mask & (1 << 1)) != 0
