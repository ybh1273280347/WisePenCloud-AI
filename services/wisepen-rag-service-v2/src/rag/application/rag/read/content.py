"""按页或 Section 获取已发布正文。"""

from collections.abc import Sequence

from rag.domain.read_content import (
    ContentWindow,
    SectionContent,
)
from rag.domain.repositories.applied_content_reader import AppliedContentReader


class ContentNotFoundError(RuntimeError):
    """资源没有可读取的 applied revision。"""


async def get_pages(
    reader: AppliedContentReader,
    *,
    resource_id: str,
    page_labels: Sequence[str],
) -> dict[str, ContentWindow]:
    pages = await reader.get_applied_pages(resource_id, page_labels)
    if pages is None:
        raise ContentNotFoundError(resource_id)
    return pages


async def get_sections(
    reader: AppliedContentReader,
    *,
    resource_id: str,
    section_ids: Sequence[str],
) -> dict[str, SectionContent]:
    sections = await reader.get_applied_sections(resource_id, section_ids)
    if sections is None:
        raise ContentNotFoundError(resource_id)
    return sections
