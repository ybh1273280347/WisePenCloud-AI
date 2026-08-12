"""已发布正文读取契约。"""

from collections.abc import Sequence
from typing import Protocol

from rag.domain.read_content import (
    ContentWindow,
    SectionContent,
)


class AppliedContentReader(Protocol):
    """按页或 Section 获取 applied revision 正文。"""

    async def get_applied_pages(
        self,
        resource_id: str,
        page_labels: Sequence[str],
    ) -> dict[str, ContentWindow] | None: ...

    async def get_applied_sections(
        self,
        resource_id: str,
        section_ids: Sequence[str],
    ) -> dict[str, SectionContent] | None: ...
