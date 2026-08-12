"""ContentReader 的 Beanie adapter。"""

from collections.abc import Sequence

from pymongo import ASCENDING

from rag.core.persistence.mongo.content_records import (
    read_source_spans,
    to_content_revision,
    to_reading_block,
    to_section,
)
from rag.domain.content_revision import ContentRevision
from rag.domain.document_structure import Section
from rag.domain.entities import (
    ContentRevisionEntity,
    ReadingBlockEntity,
    ResourceIndexStateEntity,
    SectionEntity,
    SourcePartEntity,
)
from rag.domain.read_content import (
    ContentWindow,
    DocumentStructureResult,
    SectionContent,
    SectionFrontier,
)
from rag.domain.reading import ReadingBlock
from rag.domain.repositories.content_reader import ContentReader
from rag.utils.chunkers import SourceSpan


class MongoContentReader(ContentReader):
    """只从 Beanie entities 读取 applied revision。"""

    async def read_applied_document_structure(
        self,
        resource_id: str,
    ) -> DocumentStructureResult | None:
        revision = await self._read_applied_revision(resource_id)
        if revision is None:
            return None
        entities = await SectionEntity.find(
            {
                "resource_id": resource_id,
                "content_revision": revision.content_revision,
            }
        ).sort("+own_start").to_list()
        return DocumentStructureResult(
            revision=revision,
            sections=[to_section(entity.model_dump()) for entity in entities],
        )

    async def read_applied_pages(
        self,
        resource_id: str,
        page_labels: Sequence[str],
    ) -> dict[str, ContentWindow] | None:
        revision = await self._read_applied_revision(resource_id)
        if revision is None:
            return None
        requested_labels = list(dict.fromkeys(page_labels))
        pages_by_label = {page.page_label: page for page in revision.pages}
        selected_pages = [
            pages_by_label[label] for label in requested_labels if label in pages_by_label
        ]
        windows: dict[str, ContentWindow] = {}
        for page in selected_pages:
            text = await self._read_source_text(revision.content_revision, [page.source_span])
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
                to_reading_block(entity.model_dump())
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

    async def read_applied_sections(
        self,
        resource_id: str,
        section_ids: Sequence[str],
    ) -> dict[str, SectionContent] | None:
        revision = await self._read_applied_revision(resource_id)
        if revision is None:
            return None
        requested_ids = list(dict.fromkeys(section_ids))
        if not requested_ids:
            return {}
        entities = await SectionEntity.find(
            {
                "resource_id": resource_id,
                "content_revision": revision.content_revision,
            }
        ).sort("+own_start").to_list()
        all_sections = [to_section(entity.model_dump()) for entity in entities]
        sections_by_id = {section.section_id: section for section in all_sections}
        selected = [sections_by_id[section_id] for section_id in requested_ids if section_id in sections_by_id]
        if not selected:
            return {}
        blocks = await ReadingBlockEntity.find(
            {
                "resource_id": resource_id,
                "content_revision": revision.content_revision,
                "section_id": {"$in": [section.section_id for section in selected]},
            }
        ).sort([("section_id", ASCENDING), ("ordinal", ASCENDING)]).to_list()
        blocks_by_section: dict[str, list[ReadingBlock]] = {}
        for entity in blocks:
            block = to_reading_block(entity.model_dump())
            blocks_by_section.setdefault(block.section_id, []).append(block)
        siblings_by_parent: dict[str | None, list[Section]] = {}
        for section in all_sections:
            siblings_by_parent.setdefault(section.parent_section_id, []).append(section)
        for siblings in siblings_by_parent.values():
            siblings.sort(key=lambda section: section.ordinal)
        result: dict[str, SectionContent] = {}
        for section in selected:
            siblings = siblings_by_parent[section.parent_section_id]
            index = next(i for i, sibling in enumerate(siblings) if sibling.section_id == section.section_id)
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

    async def _read_applied_revision(self, resource_id: str) -> ContentRevision | None:
        state = await ResourceIndexStateEntity.find_one({"resource_id": resource_id})
        if state is None or state.applied_content_revision is None:
            return None
        entity = await ContentRevisionEntity.find_one(
            {
                "resource_id": resource_id,
                "content_revision": state.applied_content_revision,
            }
        )
        if entity is None:
            raise RuntimeError(f"resource {resource_id} applied revision is missing")
        return to_content_revision(entity.model_dump())

    async def _read_source_text(
        self,
        content_revision: str,
        source_spans: Sequence[SourceSpan],
    ) -> str:
        entities = await SourcePartEntity.find(
            {
                "content_revision": content_revision,
                "start_offset": {"$lt": max(span.end_offset for span in source_spans)},
                "end_offset": {"$gt": min(span.start_offset for span in source_spans)},
            }
        ).sort("+part_index").to_list()
        return read_source_spans(
            content_revision=content_revision,
            documents=[entity.model_dump() for entity in entities],
            source_spans=source_spans,
        )
