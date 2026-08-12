"""ACL application 向检索和图后端同步权限事实所需的写入 port。"""

from typing import Protocol

from rag.domain.acl import ResourceAcl


class RetrievalAclWriter(Protocol):
    async def synchronize(self, resource_acl: ResourceAcl) -> None: ...


class GraphAclWriter(Protocol):
    async def initialize(self) -> None: ...

    async def synchronize(self, resource_acl: ResourceAcl) -> None: ...
