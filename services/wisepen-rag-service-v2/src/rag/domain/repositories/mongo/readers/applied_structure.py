"""已发布文档结构读取仓储契约。"""

from typing import Protocol

from rag.domain.read_content import DocumentStructureResult


class AppliedStructureReader(Protocol):
    """只读取 applied revision 的结构事实，不读取正文。"""

    async def get_applied_document_structure(
        self,
        resource_id: str,
    ) -> DocumentStructureResult | None: ...
