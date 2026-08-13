"""已发布正文读取 port 的 Beanie adapter。"""

from collections.abc import Sequence

from pymongo import ASCENDING

from rag.domain.entities import ReadingBlockEntity, SectionEntity
from rag.domain.models.content import ContentWindow, SectionContent, SectionFrontier
from rag.domain.models.content import ReadingBlock
from rag.domain.models.structure import Section
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

        windows: dict[str, ContentWindow] = {}
        for page in selected_pages:
            parts = await self._source_parts.get_parts(
                revision.content_revision,
                [page.source_span],
            )
            text = assemble_source_text(parts, [page.source_span])

            sections = await SectionEntity.find(
                {
                    "resource_id": resource_id,
                    "content_revision": revision.content_revision,
                    "own_start": {"$lt": page.source_span.end_offset},
                    "own_end": {"$gt": page.source_span.start_offset},
                }
            ).to_list()

            blocks = await ReadingBlockEntity.find(
                {
                    "resource_id": resource_id,
                    "content_revision": revision.content_revision,
                    "start_offset": {"$lt": page.source_span.end_offset},
                    "end_offset": {"$gt": page.source_span.start_offset},
                }
            ).to_list()

            page_blocks = [
                _to_reading_block(entity)
                for entity in blocks
                if any(
                    span.start_offset < page.source_span.end_offset
                    and span.end_offset > page.source_span.start_offset
                    for span in entity.source_spans
                )
            ]

            windows[page.page_label] = ContentWindow(
                text=text,
                source_span=page.source_span,
                source_spans=[page.source_span],
                page_labels=[page.page_label],
                section_ids=[section.section_id for section in sections],
                anchor_labels=list(
                    dict.fromkeys(
                        label for block in page_blocks for label in block.anchor_labels
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

        blocks = (
            await ReadingBlockEntity.find(
                {
                    "resource_id": resource_id,
                    "content_revision": revision.content_revision,
                    "section_id": {"$in": [section.section_id for section in selected]},
                }
            )
            .sort([("section_id", ASCENDING), ("ordinal", ASCENDING)])
            .to_list()
        )

        blocks_by_section: dict[str, list[ReadingBlock]] = {}
        for entity in blocks:
            block = _to_reading_block(entity)
            blocks_by_section.setdefault(block.section_id, []).append(block)

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
                reading_blocks=blocks_by_section.get(section.section_id, []),
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
        preview=record.preview,
    )


def _to_reading_block(record: ReadingBlockEntity) -> ReadingBlock:
    return ReadingBlock(
        block_id=record.block_id,
        section_id=record.section_id,
        ordinal=record.ordinal,
        raw_text=record.raw_text,
        source_spans=[
            SourceSpan(span.start_offset, span.end_offset)
            for span in record.source_spans
        ],
        page_labels=list(record.page_labels),
        anchor_labels=list(record.anchor_labels),
    )