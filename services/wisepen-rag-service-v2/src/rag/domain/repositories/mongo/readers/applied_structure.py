"""已发布文档结构读取 port 及其 persistence 快照契约。"""

from dataclasses import dataclass, field
from typing import Protocol

from rag.domain.models.content import ContentRevision
from rag.domain.models.structure import PageRange, Section


@dataclass(slots=True)
class AppliedStructureSnapshot:
    """Mongo 返回的结构事实快照，不是对外 API 结果。"""

    revision: ContentRevision
    sections: list[Section] = field(default_factory=list)
    pages: list[PageRange] = field(default_factory=list)


class AppliedStructureReader(Protocol):
    """只读取 applied revision 的结构事实，不读取正文。"""

    async def get_applied_document_structure(
        self,
        resource_id: str,
    ) -> AppliedStructureSnapshot | None: ...
