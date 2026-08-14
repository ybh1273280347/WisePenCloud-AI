"""当前已发布资源的统一读取契约。"""

from collections.abc import Sequence
from typing import Protocol

from rag.domain.models.content import (
    ContentRevision,
    ContentWindow,
    PublishedDocumentStructure,
    SectionContent,
)
from rag.domain.models.graph import GraphBuildSource
from rag.domain.models.provenance import SourceEvidence


class PublishedResourceRevisionError(RuntimeError):
    """请求 revision 已不再是资源当前发布版本。"""


class PublishedResourceCorruptError(RuntimeError):
    """已发布资源的正文、引用或结构归属不一致。"""


class PublishedResourceReader(Protocol):
    """从同一发布资源聚合读取 revision、结构、正文和来源证据。"""

    async def get_revision(self, resource_id: str) -> ContentRevision | None: ...

    async def get_document_structure(
        self,
        resource_id: str,
    ) -> PublishedDocumentStructure | None: ...

    async def get_pages(
        self,
        resource_id: str,
        page_labels: Sequence[str],
    ) -> dict[str, ContentWindow] | None: ...

    async def get_sections(
        self,
        resource_id: str,
        section_ids: Sequence[str],
    ) -> dict[str, SectionContent] | None: ...

    async def get_source_evidence(
        self,
        resource_id: str,
        content_revision: str,
        source_ref_ids: Sequence[str],
    ) -> dict[str, SourceEvidence] | None: ...

    async def get_graph_build_source(
        self,
        resource_id: str,
        content_revision: str,
    ) -> GraphBuildSource: ...
