"""读取已发布文档目录，不读取 page 或 Section 正文。"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from rag.application.rag.acl import PermissionAuthorizer
from rag.domain.models.acl import PermissionScope
from rag.domain.models.structure import PageRange, Section
from rag.domain.repositories.mongo import PublishedResourceReader

from .content import (
    ContentAccessRevokedError,
    ContentNotFoundError,
    format_page_range,
)


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

    resource_id: str
    content_revision: str
    document_version: int
    total_length: int
    outline: list[DocumentOutlineNode] = field(default_factory=list)


class DocumentOutlineReader:
    """校验权限并把 Mongo 结构事实投影为文档目录。"""

    __slots__ = ("_authorizer", "_structure_reader")

    def __init__(
        self,
        *,
        structure_reader: PublishedResourceReader,
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
        # 首次校验，避免无权限的资源被读取到结构事实。
        if not await self._authorizer.authorize_resource(
            resource_id=resource_id,
            scope=permission_scope,
        ):
            raise ContentNotFoundError(resource_id)

        structure = await self._structure_reader.get_document_structure(resource_id)
        if structure is None:
            raise ContentNotFoundError(resource_id)

        # 返回前再次校验，避免读取期间资源失去可读权限。
        if not await self._authorizer.authorize_resource(
            resource_id=resource_id,
            scope=permission_scope,
        ):
            raise ContentAccessRevokedError(resource_id)

        return DocumentOutlineResult(
            resource_id=structure.resource_id,
            content_revision=structure.content_revision,
            document_version=structure.document_version,
            total_length=structure.total_length,
            outline=_to_outline(structure.sections, structure.pages),
        )


def _to_outline(
    sections: list[Section],
    pages: list[PageRange],
) -> list[DocumentOutlineNode]:
    if not sections:
        return []

    children_by_parent: dict[str | None, list[Section]] = defaultdict(list)
    # SECTIONED 有且仅有一个虚拟根 (level == 0)；FLAT_TEXT 顶层全是 level 1 的合成 Section。
    root_section: Section | None = None
    for section in sections:
        children_by_parent[section.parent_section_id].append(section)
        if section.parent_section_id is None and section.level == 0:
            root_section = section

    # 按出现顺序排列子节点
    for children in children_by_parent.values():
        children.sort(
            key=lambda section: (section.ordinal, section.own_span.start_offset)
        )

    # FLAT_TEXT：无虚拟根，顶层合成 Section 直接逐个投影为大纲节点。
    if root_section is None:
        return [
            _to_outline_node(
                section=section,
                children_by_parent=children_by_parent,
                pages=pages,
            )
            for section in children_by_parent[None]
        ]

    # SECTIONED：root 的直接子标题作为大纲根；root 带合成标题（存在前言）时，
    # 前言作为独立叶子节点置顶展示，避免"前言包含整篇文档"的树形误导。
    nodes: list[DocumentOutlineNode] = []
    if root_section.title:
        nodes.append(
            _to_outline_node(
                section=root_section,
                children_by_parent=children_by_parent,
                pages=pages,
                expand_children=False,
            )
        )
    nodes.extend(
        _to_outline_node(
            section=section,
            children_by_parent=children_by_parent,
            pages=pages,
        )
        for section in children_by_parent[root_section.section_id]
    )
    return nodes


def _to_outline_node(
    *,
    section: Section,
    children_by_parent: dict[str | None, list[Section]],
    pages: list[PageRange],
    expand_children: bool = True,
) -> DocumentOutlineNode:
    """递归构建目录节点；前言节点不向下展开，避免重复出现同级标题。"""
    # level 0 的前言节点用 own_span 计算页范围；其 subtree_span 覆盖全文，会误报整篇页码。
    span = section.subtree_span if section.level > 0 else section.own_span
    page_labels = [
        page.page_label
        for page in pages
        if _overlaps(
            span.start_offset,
            span.end_offset,
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
            for child in (
                children_by_parent.get(section.section_id, [])
                if expand_children
                else []
            )
        ],
    )


def _overlaps(start_offset: int, end_offset: int, page: PageRange) -> bool:
    return (
        start_offset < page.source_span.end_offset
        and end_offset > page.source_span.start_offset
    )
