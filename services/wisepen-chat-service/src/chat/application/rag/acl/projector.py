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
    """把 resource-service resource item 权限数据投影为 RAG VIEW 检索权限模型。

    ACL 重算 Kafka 消息只携带 resourceId/triggerSource。RAG evidence 会进入模型上下文，
    因此这里必须从 resource item 的原始 mask 回源计算 VIEW/read 投影，不能复用搜索
    发现性使用的 DISCOVER 投影。
    """

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
            if not isinstance(group_id, str) or not group_id.strip():
                continue
            group_id = group_id.strip()
            if group_id in market_group_ids or not isinstance(acl, Mapping):
                continue

            is_readable = self._has_view(acl.get("baseMask"))
            user_masks = acl.get("userMasks")
            readable_users: tuple[str, ...] = ()
            excluded_read_users: tuple[str, ...] = ()
            if isinstance(user_masks, Mapping):
                readable_users = tuple(
                    user_id.strip()
                    for user_id, mask in user_masks.items()
                    if isinstance(user_id, str)
                    and user_id.strip()
                    and self._has_view(mask)
                    and not is_readable
                )
                excluded_read_users = tuple(
                    user_id.strip()
                    for user_id, mask in user_masks.items()
                    if isinstance(user_id, str)
                    and user_id.strip()
                    and is_readable
                    and not self._has_view(mask)
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
            group_id = item.get("groupId")
            if isinstance(group_id, str) and group_id.strip():
                market_group_ids.add(group_id.strip())
        return market_group_ids

    def _read_readable_users(self, value: Any) -> tuple[str, ...]:
        if not isinstance(value, Mapping):
            return ()
        return tuple(
            user_id.strip()
            for user_id, mask in value.items()
            if isinstance(user_id, str) and user_id.strip() and self._has_view(mask)
        )

    def _read_required_string(self, payload: Mapping[str, Any], key: str) -> str:
        value = payload.get(key)
        if value is None:
            raise RagAclProjectionError(f"{key} is required.")
        if not isinstance(value, str):
            raise RagAclProjectionError(f"{key} must be a string.")
        text = value.strip()
        if not text:
            raise RagAclProjectionError(f"{key} must not be empty.")
        return text

    def _has_view(self, mask: Any) -> bool:
        if isinstance(mask, bool) or not isinstance(mask, int):
            return False
        return (mask & _VIEW_MASK) != 0
