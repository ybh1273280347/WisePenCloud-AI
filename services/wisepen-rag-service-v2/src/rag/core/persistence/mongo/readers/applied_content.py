"""已发布正文读取 port 的 Beanie adapter。"""

from collections.abc import Sequence

from rag.domain.entities import SectionEntity
from rag.domain.models.content import (
    ContentWindow,
    SectionContent,
    SectionFrontier,
)
from rag.domain.models.structure import DocumentAnchor, PageRange, Section
from rag.domain.repositories.mongo.readers.applied_content import AppliedContentReader
from rag.domain.repositories.mongo.readers.applied_revision import AppliedRevisionReader
from rag.domain.repositories.mongo.readers.source_parts import SourcePartReader
from rag.utils.chunkers import SourceSpan

from ..text_assembler import assemble_source_text


class MongoAppliedContentReader(AppliedContentReader):
    """只从 Beanie entities 读取 applied revision 正文。"""

    def __init__(
        self,
        revisions: AppliedRevisionReader,
        source_parts: SourcePartReader,
    ) -> None:
        self._revisions = revisions
        self._source_parts = source_parts

    async def get_applied_pages(
        self,
        resource_id: str,
        page_labels: Sequence[str],
    ) -> dict[str, ContentWindow] | None:
        revision = await self._revisions.get_applied_revision(resource_id)
        if revision is None:
            return None

        requested_labels = list(dict.fromkeys(page_labels))
        pages_by_label = {page.page_label: page for page in revision.pages}
        selected_pages = [
            pages_by_label[label]
            for label in requested_labels
            if label in pages_by_label
        ]

        section_entities = (
            await SectionEntity.find(
                {
                    "resource_id": resource_id,
                    "content_revision": revision.content_revision,
                }
            )
            .sort("+own_start")
            .to_list()
        )
        all_sections = [_to_section(entity) for entity in section_entities]

        windows: dict[str, ContentWindow] = {}
        for page in selected_pages:
            parts = await self._source_parts.get_parts(
                revision.content_revision,
                [page.source_span],
            )
            text = assemble_source_text(parts, [page.source_span])

            # Page 入口来自标题或权威直属正文的交集，不借用检索分块推断结构。
            sections = [
                section
                for section in all_sections
                if page.source_span.start_offset
                <= section.own_span.start_offset
                < page.source_span.end_offset
                or any(_overlaps(span, page.source_span) for span in section.content_spans)
            ]

            windows[page.page_label] = ContentWindow(
                text=text,
                source_span=page.source_span,
                page_labels=[page.page_label],
                sections=sections,
                anchor_labels=list(
                    dict.fromkeys(
                        anchor.label
                        for anchor in revision.anchors
                        if _overlaps(anchor.source_span, page.source_span)
                    )
                ),
            )

        return windows

    async def get_applied_sections(
        self,
        resource_id: str,
        section_ids: Sequence[str],
    ) -> dict[str, SectionContent] | None:
        revision = await self._revisions.get_applied_revision(resource_id)
        if revision is None:
            return None

        requested_ids = list(dict.fromkeys(section_ids))
        if not requested_ids:
            return {}

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
        all_sections = [_to_section(entity) for entity in entities]
        sections_by_id = {section.section_id: section for section in all_sections}

        selected = [
            sections_by_id[section_id]
            for section_id in requested_ids
            if section_id in sections_by_id
        ]
        if not selected:
            return {}

        requested_spans = [
            span
            for section in selected
            for span in section.content_spans
        ]
        parts = (
            await self._source_parts.get_parts(
                revision.content_revision,
                requested_spans,
            )
            if requested_spans
            else []
        )

        siblings_by_parent: dict[str | None, list[Section]] = {}
        for section in all_sections:
            siblings_by_parent.setdefault(section.parent_section_id, []).append(section)

        for siblings in siblings_by_parent.values():
            siblings.sort(key=lambda section: section.ordinal)

        result: dict[str, SectionContent] = {}
        for section in selected:
            siblings = siblings_by_parent[section.parent_section_id]
            index = next(
                i
                for i, sibling in enumerate(siblings)
                if sibling.section_id == section.section_id
            )

            result[section.section_id] = SectionContent(
                section=section,
                text=assemble_source_text(parts, section.content_spans),
                page_labels=_overlapping_labels(section.content_spans, revision.pages),
                anchor_labels=_overlapping_labels(
                    section.content_spans,
                    revision.anchors,
                ),
                frontier=SectionFrontier(
                    parent=sections_by_id.get(section.parent_section_id),
                    previous=siblings[index - 1] if index else None,
                    next=siblings[index + 1] if index + 1 < len(siblings) else None,
                    children=siblings_by_parent.get(section.section_id, []),
                ),
            )

        return result


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
        content_spans=[
            SourceSpan(span.start_offset, span.end_offset)
            for span in record.content_spans
        ],
        preview=record.preview,
    )


def _overlaps(left: SourceSpan, right: SourceSpan) -> bool:
    return (
        left.start_offset < right.end_offset
        and right.start_offset < left.end_offset
    )


def _overlapping_labels(
    source_spans: Sequence[SourceSpan],
    labeled_ranges: Sequence[PageRange | DocumentAnchor],
) -> list[str]:
    """按文档顺序投影页码或锚点标签，空正文不制造归属信息。"""
    return list(
        dict.fromkeys(
            item.page_label if isinstance(item, PageRange) else item.label
            for item in labeled_ranges
            if any(_overlaps(span, item.source_span) for span in source_spans)
        )
    )
