"""ACL application 读取本地资源授权事实的仓储契约。"""

from collections.abc import Mapping, Sequence
from typing import Protocol

from rag.domain.acl import ResourceAcl


class ResourceAclReader(Protocol):
    """读取已同步 ACL；缺失资源不会被隐式授权。"""

    async def get_resource_acls(
        self,
        resource_ids: Sequence[str],
    ) -> Mapping[str, ResourceAcl]: ...
