"""READ 能力需要的读取 port。

这些 port 返回的是 READ 用例视图，不是领域核心事实，因此归 application/rag/read
所有；Mongo 只实现该能力需要的查询边界。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from .content import ContentWindow, SectionContent
    from .structure import DocumentStructureResult


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


class AppliedStructureReader(Protocol):
    """只读取 applied revision 的结构事实，不读取正文。"""

    async def get_applied_document_structure(
        self,
        resource_id: str,
    ) -> DocumentStructureResult | None: ...
