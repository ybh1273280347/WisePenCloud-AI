"""read 能力需要的 applied 内容读取契约。"""

from collections.abc import Sequence
from typing import Protocol

from rag.domain.read_content import (
    ContentWindow,
    DocumentStructureResult,
    SectionContent,
)


class ContentReader(Protocol):
    async def read_applied_document_structure(
        self,
        resource_id: str,
    ) -> DocumentStructureResult | None: ...

    async def read_applied_pages(
        self,
        resource_id: str,
        page_labels: Sequence[str],
    ) -> dict[str, ContentWindow] | None: ...

    async def read_applied_sections(
        self,
        resource_id: str,
        section_ids: Sequence[str],
    ) -> dict[str, SectionContent] | None: ...
