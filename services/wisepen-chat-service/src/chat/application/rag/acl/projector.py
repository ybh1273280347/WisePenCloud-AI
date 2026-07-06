from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .core import (
    RagAclProjectionError,
    RagComputedGroupAclProjection,
    RagResourceAclProjection,
)

_DISCOVER_MASK = 1


class RagAclProjectionProjector:
    """把 resource-service 权限数据投影为 RAG 检索权限模型。"""

    def has_projection_payload(self, payload: Mapping[str, Any]) -> bool:
        return "ownerId" in payload and "computedGroupAcls" in payload

    def from_projection_payload(self, payload: Mapping[str, Any]) -> RagResourceAclProjection:
        return RagResourceAclProjection(
            resource_id=self._read_required_string(payload, "resourceId"),
            owner_id=self._read_required_string(payload, "ownerId"),
            specified_discover_users=self._read_string_tuple(payload.get("specifiedDiscoverUsers")),
            computed_group_acls=self._read_projection_group_acls(payload.get("computedGroupAcls")),
        )

    def from_resource_item(self, raw: Mapping[str, Any]) -> RagResourceAclProjection:
        resource_id = self._read_required_string(raw, "_id")
        owner_id = self._read_required_string(raw, "ownerId")
        market_group_ids = self._read_market_group_ids(raw.get("groupBinds"))

        return RagResourceAclProjection(
            resource_id=resource_id,
            owner_id=owner_id,
            specified_discover_users=self._read_specified_discover_users(
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
                    is_discover=self._read_required_bool(item, "isDiscover"),
                    specified_users=self._read_string_tuple(item.get("specifiedUsers")),
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

            is_discover = self._has_discover(acl.get("baseMask"))
            user_masks = acl.get("userMasks")
            specified_users = (
                tuple(
                    str(user_id)
                    for user_id, mask in user_masks.items()
                    if self._has_discover(mask) != is_discover
                )
                if isinstance(user_masks, Mapping)
                else ()
            )
            projections.append(
                RagComputedGroupAclProjection(
                    group_id=group_id,
                    is_discover=is_discover,
                    specified_users=specified_users,
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

    def _read_specified_discover_users(self, value: Any) -> tuple[str, ...]:
        if not isinstance(value, Mapping):
            return ()
        return tuple(
            str(user_id)
            for user_id, mask in value.items()
            if self._has_discover(mask)
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

    def _has_discover(self, mask: Any) -> bool:
        try:
            return (int(mask or 0) & _DISCOVER_MASK) != 0
        except (TypeError, ValueError):
            return False
