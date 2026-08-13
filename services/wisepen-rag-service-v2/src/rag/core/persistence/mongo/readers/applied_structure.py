"""已发布文档结构读取 port 的 Beanie adapter。"""

from collections import defaultdict

from rag.domain.entities import SectionEntity
from rag.domain.models.content import DocumentStructureResult
from rag.domain.models.structure import PageRange, Section, SectionTreeNode
from rag.domain.repositories.mongo.readers.applied_revision import AppliedRevisionReader
from rag.domain.repositories.mongo.readers.applied_structure import (
    AppliedStructureReader,
)
from rag.utils.chunkers import SourceSpan


class MongoAppliedStructureReader(AppliedStructureReader):
    """只返回 applied revision 的结构事实和标题树，不读取正文。"""

    def __init__(self, *, revisions: AppliedRevisionReader) -> None:
        self._revisions = revisions

    async def get_applied_document_structure(
        self,
        resource_id: str,
    ) -> DocumentStructureResult | None:
        revision = await self._revisions.get_applied_revision(resource_id)
        if revision is None:
            return None
        entities = (
            await SectionEntity.find(
                {
                    "resource_id": resource_id,
                    "content_revision": revision.content_revision,
                }
            )
            .sort("+own_start")
            .to_list()
        )
        sections = [_to_section(entity) for entity in entities]
        return DocumentStructureResult(
            revision=revision,
            sections=sections,
            section_tree=_to_section_tree(sections, revision.pages),
            pages=list(revision.pages),
        )


def _to_section(record: SectionEntity) -> Section:
    return Section(
        section_id=record.section_id,
        title=record.title,
        level=record.level,
        parent_section_id=record.parent_section_id,
        ordinal=record.ordinal,
        section_path=list(record.section_path),
        own_span=SourceSpan(record.own_start, record.own_end),
        subtree_span=SourceSpan(record.own_start, record.subtree_end),
        preview=record.preview,
    )


def _to_section_tree(
    sections: list[Section],
    pages: list[PageRange],
) -> list[SectionTreeNode]:
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
        children.sort(
            key=lambda section: (section.ordinal, section.own_span.start_offset)
        )

    if root_section_id is not None:
        root_sections = children_by_parent.get(root_section_id, [])
    else:
        root_sections = [
            section for section in children_by_parent.get(None, []) if section.title
        ]

    return [
        _to_section_tree_node(
            section=section,
            children_by_parent=children_by_parent,
            pages=pages,
        )
        for section in root_sections
    ]


def _to_section_tree_node(
    *,
    section: Section,
    children_by_parent: dict[str | None, list[Section]],
    pages: list[PageRange],
) -> SectionTreeNode:
    page_labels = [
        page.page_label
        for page in pages
        if _overlaps(
            section.subtree_span.start_offset, section.subtree_span.end_offset, page
        )
    ]
    return SectionTreeNode(
        section_id=section.section_id,
        title=section.title,
        level=section.level,
        section_path=list(section.section_path),
        has_content=section.own_span.end_offset > section.own_span.start_offset,
        start_page_label=page_labels[0] if page_labels else None,
        end_page_label=page_labels[-1] if page_labels else None,
        page_labels=page_labels,
        children=[
            _to_section_tree_node(
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
