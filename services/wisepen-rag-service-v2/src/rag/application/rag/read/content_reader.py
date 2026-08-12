"""无状态读取的内容 port 与三个确定性读取动作。"""

from collections.abc import Sequence

from rag.domain.read_content import (
    ContentWindow,
    DocumentStructureResult,
    SectionContent,
)
from rag.domain.repositories.content_reader import ContentReader


class ContentNotFoundError(RuntimeError):
    """资源没有可读取的 applied revision。"""


async def read_document_structure(
    reader: ContentReader,
    *,
    resource_id: str,
) -> DocumentStructureResult:
    structure = await reader.read_applied_document_structure(resource_id)
    if structure is None:
        raise ContentNotFoundError(resource_id)
    return structure


async def read_pages(
    reader: ContentReader,
    *,
    resource_id: str,
    page_labels: Sequence[str],
) -> dict[str, ContentWindow]:
    pages = await reader.read_applied_pages(resource_id, page_labels)
    if pages is None:
        raise ContentNotFoundError(resource_id)
    return pages


async def read_sections(
    reader: ContentReader,
    *,
    resource_id: str,
    section_ids: Sequence[str],
) -> dict[str, SectionContent]:
    sections = await reader.read_applied_sections(resource_id, section_ids)
    if sections is None:
        raise ContentNotFoundError(resource_id)
    return sections
