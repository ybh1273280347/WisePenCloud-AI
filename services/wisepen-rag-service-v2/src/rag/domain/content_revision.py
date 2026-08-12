"""资源索引版本和权威原文分片事实。"""

from dataclasses import dataclass, field

from rag.domain.document_structure import PageRange, StructureMode
from rag.utils.chunkers import SourceSpan


@dataclass(slots=True)
class ResourceIndexState:
    """一个资源当前 staged/applied revision 指针。"""

    resource_id: str
    staged_content_revision: str | None = None
    staged_document_version: int | None = None
    applied_content_revision: str | None = None
    applied_document_version: int | None = None


@dataclass(slots=True)
class ContentRevision:
    """一次可独立发布的权威 Markdown 版本。"""

    resource_id: str
    content_revision: str
    document_version: int
    content_hash: str
    index_schema_version: str
    structure_mode: StructureMode
    total_length: int
    pages: list[PageRange] = field(default_factory=list)


@dataclass(slots=True)
class SourcePart:
    """超大 Markdown 的连续存储分片。"""

    resource_id: str
    content_revision: str
    part_index: int
    source_span: SourceSpan
    text: str
