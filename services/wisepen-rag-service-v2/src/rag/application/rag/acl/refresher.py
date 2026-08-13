"""从权威资源事实刷新 RAG 本地及后端 ACL。"""

import asyncio

from rag.domain.repositories.mongo.readers.authoritative_acl import (
    AuthoritativeAclReader,
)
from rag.domain.repositories.mongo.resource_acl_store import ResourceAclStore
from rag.domain.repositories.neo4j.graph_acl_writer import GraphAclWriter
from rag.domain.repositories.qdrant.retrieval_acl_writer import RetrievalAclWriter


class AuthoritativeAclNotFoundError(RuntimeError):
    """上游权威资源不存在，不能生成 RAG ACL。"""


class LocalAclStateError(RuntimeError):
    """本地 ACL 条件写入失败后无法读取当前 revision。"""


class ResourceAclRefresher:
    """保存本地 ACL 后显式同步 Qdrant 与 Neo4j，失败直接抛出。"""

    def __init__(
        self,
        *,
        authoritative_reader: AuthoritativeAclReader,
        local_store: ResourceAclStore,
        retrieval_writer: RetrievalAclWriter,
        graph_writer: GraphAclWriter,
    ) -> None:
        self._authoritative_reader = authoritative_reader
        self._local_store = local_store
        self._retrieval_writer = retrieval_writer
        self._graph_writer = graph_writer

    async def refresh(self, resource_id: str) -> None:
        resource_acl = await self._authoritative_reader.get_resource_acl(resource_id)
        if resource_acl is None:
            raise AuthoritativeAclNotFoundError(resource_id)

        saved = await self._local_store.save_if_newer(resource_acl)
        if not saved:
            current = await self._local_store.get_resource_acl(resource_acl.resource_id)
            if current is None:
                raise LocalAclStateError(resource_acl.resource_id)
            if current.acl_revision > resource_acl.acl_revision:
                resource_acl = current
                
        # 同 revision 或旧事件重试仍需把本地最高 ACL 补偿同步到后端。
        async with asyncio.TaskGroup() as tasks:
            tasks.create_task(self._retrieval_writer.synchronize(resource_acl))
            tasks.create_task(self._graph_writer.synchronize(resource_acl))
