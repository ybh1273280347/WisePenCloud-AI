"""知识图谱发布写入 port。"""

from collections.abc import Sequence
from typing import Protocol

from rag.domain.knowledge_graph import KnowledgeGraph


class KnowledgeGraphRevisionSupersededError(RuntimeError):
    """写入任务对应的内容版本已被更新版本取代。"""


class KnowledgeGraphWriter(Protocol):
    """管理资源知识图谱的 schema、构建状态和发布结果。"""

    async def initialize(self) -> None: ...

    async def begin_build(
        self,
        *,
        resource_id: str,
        content_revision: str,
        document_version: int,
    ) -> None: ...

    async def publish(
        self,
        *,
        graph: KnowledgeGraph,
        document_version: int,
    ) -> None: ...

    async def skip(
        self,
        *,
        resource_id: str,
        content_revision: str,
        document_version: int,
    ) -> None: ...

    async def delete_resources(self, resource_ids: Sequence[str]) -> None: ...
