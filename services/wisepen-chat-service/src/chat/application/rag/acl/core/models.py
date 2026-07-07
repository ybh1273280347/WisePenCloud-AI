from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RagComputedGroupAclProjection:
    """单个群组的 RAG 权限投影。

    - group_id: 群组 ID
    - is_readable: 群组整体是否有 view/read 权限
    - excluded_read_users: 群组可读时，被排除的用户
    - readable_users: 群组不可读时，被单独授权读取的用户
    """

    group_id: str
    is_readable: bool
    readable_users: tuple[str, ...] = ()
    excluded_read_users: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RagResourceAclProjection:
    """资源的 RAG 权限投影，供检索层按权限过滤 chunk。

    - resource_id: 资源 ID
    - owner_id: 资源所有者
    - readable_users: 资源级指定拥有 view/read 权限的用户
    - computed_group_acls: 各群组的权限投影
    """

    resource_id: str
    owner_id: str
    readable_users: tuple[str, ...] = ()
    computed_group_acls: tuple[RagComputedGroupAclProjection, ...] = ()
