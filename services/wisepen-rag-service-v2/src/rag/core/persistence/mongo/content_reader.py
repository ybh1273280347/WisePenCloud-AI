"""ContentReader 的 applied-only PyMongo adapter。"""

from collections.abc import Sequence

from pymongo import ASCENDING
from pymongo.asynchronous.database import AsyncDatabase

from rag.core.persistence.mongo.content_records import (
    read_source_spans,
    to_content_revision,
    to_reading_block,
    to_section,
)
from rag.domain.content_revision import ContentRevision
from rag.domain.document_structure import Section
from rag.domain.read_content import (
    ContentWindow,
    DocumentStructureResult,
    SectionContent,
    SectionFrontier,
)
from rag.domain.reading import ReadingBlock
from rag.domain.repositories.content_reader import ContentReader
from rag.utils.chunkers import SourceSpan

_RESOURCE_INDEX_STATES = "wisepen_rag_v2_resource_index_states"
_CONTENT_REVISIONS = "wisepen_rag_v2_content_revisions"
_SOURCE_PARTS = "wisepen_rag_v2_source_parts"
_SECTIONS = "wisepen_rag_v2_sections"
_READING_BLOCKS = "wisepen_rag_v2_reading_blocks"


class MongoContentReader(ContentReader):
    """所有方法先解析 applied 指针，再读取同一 revision 的内容。"""

    __slots__ = (
        "_content_revisions",
        "_reading_blocks",
        "_resource_index_states",
        "_sections",
        "_source_parts",
    )

    def __init__(self, database: AsyncDatabase | None = None) -> None:
        from rag.domain.entities import (
            ContentRevisionEntity,
            ReadingBlockEntity,
            ResourceIndexStateEntity,
            SectionEntity,
            SourcePartEntity,
        )

        if database is None:
            self._resource_index_states = ResourceIndexStateEntity.get_pymongo_collection()
            self._content_revisions = ContentRevisionEntity.get_pymongo_collection()
            self._source_parts = SourcePartEntity.get_pymongo_collection()
            self._sections = SectionEntity.get_pymongo_collection()
            self._reading_blocks = ReadingBlockEntity.get_pymongo_collection()
            return
        self._resource_index_states = database[_RESOURCE_INDEX_STATES]
        self._content_revisions = database[_CONTENT_REVISIONS]
        self._source_parts = database[_SOURCE_PARTS]
        self._sections = database[_SECTIONS]
        self._reading_blocks = database[_READING_BLOCKS]

    async def read_applied_document_structure(
        self,
        resource_id: str,
    ) -> DocumentStructureResult | None:
        revision = await self._read_applied_revision(resource_id)
        if revision is None:
            return None
        documents = await (
            self._sections.find(
                {
                    "resource_id": resource_id,
                    "content_revision": revision.content_revision,
                },
                {"_id": False},
            )
            .sort("own_start", ASCENDING)
            .to_list()
        )
        return DocumentStructureResult(
            revision=revision,
            sections=[to_section(document) for document in documents],
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
            pages_by_label[label]
            for label in requested_labels
            if label in pages_by_label
        ]
        if not selected_pages:
            return {}

        windows: dict[str, ContentWindow] = {}
        for page in selected_pages:
            text = await self._read_source_text(
                revision.content_revision,
                [page.source_span],
            )
            section_documents = await self._sections.find(
                {
                    "resource_id": resource_id,
                    "content_revision": revision.content_revision,
                    "own_start": {"$lt": page.source_span.end_offset},
                    "own_end": {"$gt": page.source_span.start_offset},
                },
                {"_id": False, "section_id": True},
            ).to_list()
            block_documents = await self._reading_blocks.find(
                {
                    "resource_id": resource_id,
                    "content_revision": revision.content_revision,
                    "start_offset": {"$lt": page.source_span.end_offset},
                    "end_offset": {"$gt": page.source_span.start_offset},
                },
                {"_id": False},
            ).to_list()
            page_blocks: list[ReadingBlock] = []
            for document in block_documents:
                block = to_reading_block(document)
                if any(
                    span.start_offset < page.source_span.end_offset
                    and span.end_offset > page.source_span.start_offset
                    for span in block.source_spans
                ):
                    page_blocks.append(block)
            windows[page.page_label] = ContentWindow(
                text=text,
                source_span=page.source_span,
                source_spans=[page.source_span],
                page_labels=[page.page_label],
                section_ids=[
                    str(document["section_id"]) for document in section_documents
                ],
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

        all_documents = await (
            self._sections.find(
                {
                    "resource_id": resource_id,
                    "content_revision": revision.content_revision,
                },
                {"_id": False},
            )
            .sort("own_start", ASCENDING)
            .to_list()
        )
        all_sections = [to_section(document) for document in all_documents]
        sections_by_id = {section.section_id: section for section in all_sections}
        selected = [
            sections_by_id[section_id]
            for section_id in requested_ids
            if section_id in sections_by_id
        ]
        if not selected:
            return {}

        block_documents = await (
            self._reading_blocks.find(
                {
                    "resource_id": resource_id,
                    "content_revision": revision.content_revision,
                    "section_id": {"$in": [section.section_id for section in selected]},
                },
                {"_id": False},
            )
            .sort([("section_id", ASCENDING), ("ordinal", ASCENDING)])
            .to_list()
        )
        blocks_by_section: dict[str, list[ReadingBlock]] = {}
        for document in block_documents:
            block = to_reading_block(document)
            blocks_by_section.setdefault(block.section_id, []).append(block)

        siblings_by_parent: dict[str | None, list[Section]] = {}
        for section in all_sections:
            siblings_by_parent.setdefault(section.parent_section_id, []).append(section)
        for siblings in siblings_by_parent.values():
            siblings.sort(key=lambda section: section.ordinal)

        result: dict[str, SectionContent] = {}
        for section in selected:
            siblings = siblings_by_parent[section.parent_section_id]
            sibling_index = next(
                index
                for index, sibling in enumerate(siblings)
                if sibling.section_id == section.section_id
            )
            result[section.section_id] = SectionContent(
                section=section,
                reading_blocks=blocks_by_section.get(section.section_id, []),
                frontier=SectionFrontier(
                    parent=(
                        sections_by_id.get(section.parent_section_id)
                        if section.parent_section_id is not None
                        else None
                    ),
                    previous=siblings[sibling_index - 1] if sibling_index > 0 else None,
                    next=(
                        siblings[sibling_index + 1]
                        if sibling_index + 1 < len(siblings)
                        else None
                    ),
                    children=siblings_by_parent.get(section.section_id, []),
                ),
            )
        return result

    async def _read_applied_revision(
        self,
        resource_id: str,
    ) -> ContentRevision | None:
        state = await self._resource_index_states.find_one(
            {"resource_id": resource_id},
            {"_id": False, "applied_content_revision": True},
        )
        if state is None or state.get("applied_content_revision") is None:
            return None
        document = await self._content_revisions.find_one(
            {
                "resource_id": resource_id,
                "content_revision": state["applied_content_revision"],
            },
            {"_id": False},
        )
        if document is None:
            raise RuntimeError(f"resource {resource_id} applied revision is missing")
        return to_content_revision(document)

    async def _read_source_text(
        self,
        content_revision: str,
        source_spans: Sequence[SourceSpan],
    ) -> str:
        documents = await (
            self._source_parts.find(
                {
                    "content_revision": content_revision,
                    "start_offset": {"$lt": max(span.end_offset for span in source_spans)},
                    "end_offset": {"$gt": min(span.start_offset for span in source_spans)},
                },
                {"_id": False},
            )
            .sort("part_index", ASCENDING)
            .to_list()
        )
        return read_source_spans(
            content_revision=content_revision,
            documents=documents,
            source_spans=source_spans,
        )
