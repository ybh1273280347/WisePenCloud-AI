"""读取已发布文档目录，不读取 page 或 Section 正文。"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from rag.application.rag.acl import PermissionAuthorizer
from rag.domain.models.acl import PermissionScope
from rag.domain.models.content import ContentRevision
from rag.domain.models.structure import PageRange, Section
from rag.domain.repositories.mongo.readers.applied_structure import (
    AppliedStructureReader,
)

from ..page_range import format_page_range
from .content import ContentAccessRevokedError, ContentNotFoundError


@dataclass(slots=True)
class DocumentOutlineNode:
    """目录节点；flat text 由 synthetic Section 提供可读取结构。"""

    section_id: str
    title: str
    section_path: str
    page_range: str | None = None
    children: list[DocumentOutlineNode] = field(default_factory=list)


@dataclass(slots=True)
class DocumentOutlineResult:
    """READ outline 面向 API 的最终返回结果。"""

    revision: ContentRevision
    outline: list[DocumentOutlineNode] = field(default_factory=list)


class DocumentOutlineReader:
    """校验权限并把 Mongo 结构事实投影为文档目录。"""

    __slots__ = ("_authorizer", "_structure_reader")

    def __init__(
        self,
        *,
        structure_reader: AppliedStructureReader,
        authorizer: PermissionAuthorizer,
    ) -> None:
        self._structure_reader = structure_reader
        self._authorizer = authorizer

    async def get_document_outline(
        self,
        *,
        resource_id: str,
        permission_scope: PermissionScope,
    ) -> DocumentOutlineResult:
        if not await self._authorizer.authorize_resource(
            resource_id=resource_id,
            scope=permission_scope,
        ):
            raise ContentNotFoundError(resource_id)

        snapshot = await self._structure_reader.get_applied_document_structure(resource_id)
        if snapshot is None:
            raise ContentNotFoundError(resource_id)

        # 返回前再次校验，避免读取期间资源失去可读权限。
        if not await self._authorizer.authorize_resource(
            resource_id=resource_id,
            scope=permission_scope,
        ):
            raise ContentAccessRevokedError(resource_id)

        return DocumentOutlineResult(
            revision=snapshot.revision,
            outline=_to_outline(snapshot.sections, snapshot.pages),
        )


def _to_outline(
    sections: list[Section],
    pages: list[PageRange],
) -> list[DocumentOutlineNode]:
    if not sections:
        return []

    children_by_parent: dict[str | None, list[Section]] = defaultdict(list)
    root_section_id: str | None = None
    for section in sections:
        children_by_parent[section.parent_section_id].append(section)
        if (
            root_section_id is None
            and section.parent_section_id is None
            and section.level == 0
            and not section.title
        ):
            root_section_id = section.section_id

    for children in children_by_parent.values():
        children.sort(key=lambda section: (section.ordinal, section.own_span.start_offset))

    if root_section_id is not None:
        root_sections = children_by_parent.get(root_section_id, [])
    else:
        root_sections = [
            section for section in children_by_parent.get(None, []) if section.title
        ]

    return [
        _to_outline_node(
            section=section,
            children_by_parent=children_by_parent,
            pages=pages,
        )
        for section in root_sections
    ]


def _to_outline_node(
    *,
    section: Section,
    children_by_parent: dict[str | None, list[Section]],
    pages: list[PageRange],
) -> DocumentOutlineNode:
    page_labels = [
        page.page_label
        for page in pages
        if _overlaps(
            section.subtree_span.start_offset,
            section.subtree_span.end_offset,
            page,
        )
    ]
    return DocumentOutlineNode(
        section_id=section.section_id,
        title=section.title,
        section_path=" > ".join(section.section_path),
        page_range=format_page_range(page_labels),
        children=[
            _to_outline_node(
                section=child,
                children_by_parent=children_by_parent,
                pages=pages,
            )
            for child in children_by_parent.get(section.section_id, [])
        ],
    )


def _overlaps(start_offset: int, end_offset: int, page: PageRange) -> bool:
    return (
        start_offset < page.source_span.end_offset
        and end_offset > page.source_span.start_offset
    )
