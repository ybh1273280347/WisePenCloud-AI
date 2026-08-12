"""按页或 Section 获取已发布正文。"""

from collections.abc import Sequence
from dataclasses import dataclass, field

from rag.application.rag.acl import PermissionAuthorizer
from rag.domain.acl import PermissionScope
from rag.domain.document_structure import Section
from rag.domain.evidence import EvidenceRecord
from rag.domain.reading import ReadingBlock
from rag.utils.chunkers import SourceSpan

from .ports import AppliedContentReader


@dataclass(slots=True)
class ContentWindow:
    """READ 返回的正文窗口，source_span 使用 Python 字符偏移。"""

    text: str
    source_span: SourceSpan
    source_spans: list[SourceSpan] = field(default_factory=list)
    page_labels: list[str] = field(default_factory=list)
    section_ids: list[str] = field(default_factory=list)
    anchor_labels: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SectionFrontier:
    """围绕一个 Section 的标题树探索边界，由 READ 构造并供 EXPAND 消费。"""

    parent: Section | None = None
    previous: Section | None = None
    next: Section | None = None
    children: list[Section] = field(default_factory=list)


@dataclass(slots=True)
class SectionContent:
    """READ 返回的 Section 正文及相邻标题入口。"""

    section: Section
    reading_blocks: list[ReadingBlock] = field(default_factory=list)
    frontier: SectionFrontier = field(default_factory=SectionFrontier)


@dataclass(slots=True)
class SectionView:
    """Agent 可读取并继续展开的标题树节点视图。"""

    resource_id: str
    content_revision: str
    section: Section
    reading_blocks: list[ReadingBlock] = field(default_factory=list)
    frontier: SectionFrontier = field(default_factory=SectionFrontier)
    evidence: list[EvidenceRecord] = field(default_factory=list)


class ContentNotFoundError(RuntimeError):
    """资源没有可读取的 applied revision。"""


class DocumentContentReader:
    """读取 applied revision 的 page 和 Section 正文。"""

    __slots__ = ("_authorizer", "_reader")

    def __init__(
        self,
        *,
        reader: AppliedContentReader,
        authorizer: PermissionAuthorizer,
    ) -> None:
        self._reader = reader
        self._authorizer = authorizer

    async def get_pages(
        self,
        *,
        resource_id: str,
        page_labels: Sequence[str],
        permission_scope: PermissionScope,
    ) -> dict[str, ContentWindow]:
        if not await self._authorizer.authorize_resource(
            resource_id=resource_id,
            scope=permission_scope,
        ):
            raise ContentNotFoundError(resource_id)
        pages = await self._reader.get_applied_pages(resource_id, page_labels)
        if pages is None:
            raise ContentNotFoundError(resource_id)
        return pages

    async def get_sections(
        self,
        *,
        resource_id: str,
        section_ids: Sequence[str],
        permission_scope: PermissionScope,
    ) -> dict[str, SectionContent]:
        if not await self._authorizer.authorize_resource(
            resource_id=resource_id,
            scope=permission_scope,
        ):
            raise ContentNotFoundError(resource_id)
        sections = await self._reader.get_applied_sections(resource_id, section_ids)
        if sections is None:
            raise ContentNotFoundError(resource_id)
        return sections
