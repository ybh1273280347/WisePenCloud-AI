"""当前 applied revision 读取契约。"""

from typing import Protocol

from rag.domain.content_revision import ContentRevision


class AppliedRevisionReader(Protocol):
    """读取资源当前已发布的内容 revision。"""

    async def get_applied_revision(
        self,
        resource_id: str,
    ) -> ContentRevision | None: ...
