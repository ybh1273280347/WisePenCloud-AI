from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .core import (
    RagAclProjectionError,
    RagComputedGroupAclProjection,
    RagResourceAclProjection,
)

_VIEW_MASK = 1 << 1  # ResourceAction.VIEW，RAG evidence 进入上下文必须具备阅读权限


class RagAclProjectionProjector:
    """把 resource-service 权限数据投影为 RAG 检索权限模型。

    支持两种输入来源：
    1. from_projection_payload — Kafka 消息中直接携带了投影数据（computedGroupAcls）
    2. from_resource_item — 从 resource-service 原始资源数据构建投影

    两者最终产出相同的 RagResourceAclProjection，供检索层按权限过滤 chunk。
    """

    def has_projection_payload(self, payload: Mapping[str, Any]) -> bool:
        """判断 Kafka 消息是否直接携带了投影数据（可跳过回源查询）。"""
        return "ownerId" in payload and "computedGroupAcls" in payload

    def from_projection_payload(self, payload: Mapping[str, Any]) -> RagResourceAclProjection:
        """从 Kafka 消息中的投影数据构建权限模型（无需回源查询）。"""
        return RagResourceAclProjection(
            resource_id=self._read_required_string(payload, "resourceId"),
            owner_id=self._read_required_string(payload, "ownerId"),
            readable_users=self._read_string_tuple(payload.get("readableUsers")),
            computed_group_acls=self._read_projection_group_acls(payload.get("computedGroupAcls")),
        )

    def from_resource_item(self, raw: Mapping[str, Any]) -> RagResourceAclProjection:
        """从 resource-service 原始资源数据构建权限模型（需要回源查询时使用）。"""
        resource_id = self._read_required_string(raw, "_id")
        owner_id = self._read_required_string(raw, "ownerId")
        market_group_ids = self._read_market_group_ids(raw.get("groupBinds"))

        return RagResourceAclProjection(
            resource_id=resource_id,
            owner_id=owner_id,
            readable_users=self._read_readable_users(
                raw.get("specifiedUsersGrantedActionsMask")
            ),
            computed_group_acls=self._read_resource_group_acls(
                raw.get("computedGroupAcls"),
                market_group_ids=market_group_ids,
            ),
        )

    def _read_projection_group_acls(self, value: Any) -> tuple[RagComputedGroupAclProjection, ...]:
        if value is None:
            return ()
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
            raise RagAclProjectionError("computedGroupAcls must be a list.")

        projections: list[RagComputedGroupAclProjection] = []
        for item in value:
            if not isinstance(item, Mapping):
                raise RagAclProjectionError("computedGroupAcls item must be an object.")
            projections.append(
                RagComputedGroupAclProjection(
                    group_id=self._read_required_string(item, "groupId"),
                    is_readable=self._read_required_bool(item, "isReadable"),
                    readable_users=self._read_string_tuple(item.get("readableUsers")),
                    excluded_read_users=self._read_string_tuple(item.get("excludedReadUsers")),
                )
            )
        return tuple(projections)

    def _read_resource_group_acls(
            self,
            value: Any,
            *,
            market_group_ids: set[str],
    ) -> tuple[RagComputedGroupAclProjection, ...]:
        if not isinstance(value, Mapping):
            return ()

        projections: list[RagComputedGroupAclProjection] = []
        for group_id, acl in value.items():
            group_id = str(group_id)
            if group_id in market_group_ids or not isinstance(acl, Mapping):
                continue

            is_readable = self._has_view(acl.get("baseMask"))
            user_masks = acl.get("userMasks")
            readable_users: tuple[str, ...] = ()
            excluded_read_users: tuple[str, ...] = ()
            if isinstance(user_masks, Mapping):
                readable_users = tuple(
                    str(user_id)
                    for user_id, mask in user_masks.items()
                    if self._has_view(mask) and not is_readable
                )
                excluded_read_users = tuple(
                    str(user_id)
                    for user_id, mask in user_masks.items()
                    if is_readable and not self._has_view(mask)
                )
            projections.append(
                RagComputedGroupAclProjection(
                    group_id=group_id,
                    is_readable=is_readable,
                    readable_users=readable_users,
                    excluded_read_users=excluded_read_users,
                )
            )
        return tuple(projections)

    def _read_market_group_ids(self, value: Any) -> set[str]:
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
            return set()

        market_group_ids: set[str] = set()
        for item in value:
            if not isinstance(item, Mapping):
                continue
            if item.get("marketSaleInfo") is None:
                continue
            group_id = str(item.get("groupId") or "").strip()
            if group_id:
                market_group_ids.add(group_id)
        return market_group_ids

    def _read_readable_users(self, value: Any) -> tuple[str, ...]:
        if not isinstance(value, Mapping):
            return ()
        return tuple(
            str(user_id)
            for user_id, mask in value.items()
            if self._has_view(mask)
        )

    def _read_required_string(self, payload: Mapping[str, Any], key: str) -> str:
        value = payload.get(key)
        if value is None:
            raise RagAclProjectionError(f"{key} is required.")
        text = str(value).strip()
        if not text:
            raise RagAclProjectionError(f"{key} must not be empty.")
        return text

    def _read_required_bool(self, payload: Mapping[str, Any], key: str) -> bool:
        value = payload.get(key)
        if isinstance(value, bool):
            return value
        raise RagAclProjectionError(f"{key} must be a boolean.")

    def _read_string_tuple(self, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
            raise RagAclProjectionError("value must be a list.")
        return tuple(str(item).strip() for item in value if str(item).strip())

    def _has_view(self, mask: Any) -> bool:
        try:
            return (int(mask or 0) & _VIEW_MASK) != 0
        except (TypeError, ValueError):
            return False
