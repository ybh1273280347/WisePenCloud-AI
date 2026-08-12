"""index 能力需要的资源内容仓储契约。"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from rag.domain.content_revision import ContentRevision, ResourceIndexState
from rag.domain.document_structure import Section
from rag.domain.reading import ReadingBlock
from rag.domain.retrieval import SourceRef
from rag.utils.chunkers import SourceSpan


class StageAction(StrEnum):
    STAGED = "staged"
    ALREADY_APPLIED = "already_applied"
    STALE = "stale"


@dataclass(slots=True)
class GraphBuildSource:
    resource_id: str
    content_revision: str
    markdown: str
    sections: list[Section] = field(default_factory=list)
    reading_blocks: list[ReadingBlock] = field(default_factory=list)
    source_refs: list[SourceRef] = field(default_factory=list)


class ResourceIndexStore(Protocol):
    async def stage_revision(
        self,
        revision: ContentRevision,
        markdown: str,
        sections: Sequence[Section],
        reading_blocks: Sequence[ReadingBlock],
        source_refs: Sequence[SourceRef],
    ) -> StageAction: ...

    async def apply_revision(self, revision: ContentRevision) -> None: ...

    async def read_state(self, resource_id: str) -> ResourceIndexState | None: ...

    async def read_revision(self, content_revision: str) -> ContentRevision | None: ...

    async def read_source_text(
        self,
        content_revision: str,
        source_spans: Sequence[SourceSpan],
    ) -> str: ...

    async def read_graph_build_source(
        self,
        resource_id: str,
        content_revision: str,
    ) -> GraphBuildSource: ...

    async def delete_resources(self, resource_ids: Sequence[str]) -> None: ...
