"""获取已发布文档结构，不读取 page 或 Section 正文。"""

from rag.domain.read_content import DocumentStructureResult
from rag.domain.repositories.applied_structure_reader import AppliedStructureReader

from .content import ContentNotFoundError


class DocumentStructureReader:
    """读取 applied revision 的结构事实，不读取正文。"""

    __slots__ = ("_reader",)

    def __init__(self, *, reader: AppliedStructureReader) -> None:
        self._reader = reader

    async def get(self, *, resource_id: str) -> DocumentStructureResult:
        structure = await self._reader.get_applied_document_structure(resource_id)
        if structure is None:
            raise ContentNotFoundError(resource_id)
        return structure
