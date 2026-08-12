"""index 写入能力需要的资源索引仓储契约。"""

from collections.abc import Sequence
from enum import StrEnum
from typing import Protocol

from rag.domain.content_revision import ContentRevision
from rag.domain.document_structure import Section
from rag.domain.reading import ReadingBlock
from rag.domain.retrieval import SourceRef


class StageAction(StrEnum):
    STAGED = "staged"
    ALREADY_APPLIED = "already_applied"
    STALE = "stale"


class ResourceIndexWriter(Protocol):
    """写入并发布资源索引 revision，不对外提供内容读取。"""

    async def stage_revision(
        self,
        revision: ContentRevision,
        markdown: str,
        sections: Sequence[Section],
        reading_blocks: Sequence[ReadingBlock],
        source_refs: Sequence[SourceRef],
    ) -> StageAction: ...

    async def apply_revision(self, revision: ContentRevision) -> None: ...

    async def delete_other_revisions(
        self,
        *,
        resource_id: str,
        keep_content_revision: str,
    ) -> None: ...

    async def clear_resource_states(self, resource_ids: Sequence[str]) -> None: ...

    async def delete_resources(self, resource_ids: Sequence[str]) -> None: ...
