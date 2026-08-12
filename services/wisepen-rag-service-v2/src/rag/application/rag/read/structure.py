"""获取已发布文档结构，不读取 page 或 Section 正文。"""

from rag.domain.read_content import DocumentStructureResult
from rag.domain.repositories.applied_structure_reader import AppliedStructureReader

from .content import ContentNotFoundError


async def get_document_structure(
    reader: AppliedStructureReader,
    *,
    resource_id: str,
) -> DocumentStructureResult:
    structure = await reader.get_applied_document_structure(resource_id)
    if structure is None:
        raise ContentNotFoundError(resource_id)
    return structure
