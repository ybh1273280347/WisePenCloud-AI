from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RagComputedGroupAclProjection:
    group_id: str
    is_discover: bool
    specified_users: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RagResourceAclProjection:
    resource_id: str
    owner_id: str
    specified_discover_users: tuple[str, ...] = ()
    computed_group_acls: tuple[RagComputedGroupAclProjection, ...] = ()
