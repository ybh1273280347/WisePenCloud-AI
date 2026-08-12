"""Resource index writer backed by Beanie entities."""

from collections.abc import Sequence

from pymongo.errors import DuplicateKeyError

from rag.application.rag.index.revisions import build_content_revision_id, decide_stage
from rag.domain.content_revision import ContentRevision, ResourceIndexState, SourcePart
from rag.domain.document_structure import Section
from rag.domain.entities import (
    ContentRevisionEntity,
    ReadingBlockEntity,
    ResourceIndexStateEntity,
    SectionEntity,
    SourcePartEntity,
    SourceRefEntity,
)
from rag.domain.reading import ReadingBlock
from rag.domain.repositories import ResourceIndexWriter, StageAction
from rag.domain.retrieval import SourceRef
from rag.utils.chunkers import SourceSpan

_SOURCE_PART_CHARACTERS = 1_000_000


class MongoResourceIndexWriter(ResourceIndexWriter):
    """通过 Beanie entities 管理 staged/applied 内容 revision。"""

    async def stage_revision(
        self,
        revision: ContentRevision,
        markdown: str,
        sections: Sequence[Section],
        reading_blocks: Sequence[ReadingBlock],
        source_refs: Sequence[SourceRef],
    ) -> StageAction:
        if revision.total_length != len(markdown):
            raise ValueError("content revision length does not match markdown")
        expected_revision = build_content_revision_id(
            resource_id=revision.resource_id,
            document_version=revision.document_version,
            markdown=markdown,
            index_schema_version=revision.index_schema_version,
        )
        if revision.content_revision != expected_revision:
            raise ValueError("content revision identity does not match markdown")
        _validate_structure_records(
            revision=revision,
            sections=sections,
            reading_blocks=reading_blocks,
            source_refs=source_refs,
        )
        action = decide_stage(revision, await self._get_state(revision.resource_id))
        if action is not StageAction.STAGED:
            return action

        stored_revision = ContentRevisionEntity(**_revision_document(revision))
        existing_revision = await ContentRevisionEntity.find_one(
            {"content_revision": revision.content_revision}
        )
        if existing_revision is None:
            await stored_revision.insert()
        else:
            stored_revision.id = existing_revision.id
            await stored_revision.replace()

        await SourcePartEntity.find(
            {"content_revision": revision.content_revision}
        ).delete_many()
        parts = split_source_parts(revision, markdown)
        if parts:
            await SourcePartEntity.insert_many(
                [SourcePartEntity(**_source_part_document(part)) for part in parts]
            )
        for entity_type in (SectionEntity, ReadingBlockEntity, SourceRefEntity):
            await entity_type.find(
                {"content_revision": revision.content_revision}
            ).delete_many()
        if sections:
            await SectionEntity.insert_many(
                [
                    SectionEntity(**_section_document(revision, section))
                    for section in sections
                ]
            )
        if reading_blocks:
            await ReadingBlockEntity.insert_many(
                [
                    ReadingBlockEntity(**_reading_block_document(revision, block))
                    for block in reading_blocks
                ]
            )
        if source_refs:
            await SourceRefEntity.insert_many(
                [
                    SourceRefEntity(**_source_ref_document(revision, source_ref))
                    for source_ref in source_refs
                ]
            )

        state_collection = ResourceIndexStateEntity.get_pymongo_collection()
        try:
            result = await state_collection.update_one(
                _stage_state_filter(revision),
                {
                    "$set": {
                        "staged_content_revision": revision.content_revision,
                        "staged_document_version": revision.document_version,
                    },
                    "$setOnInsert": {"resource_id": revision.resource_id},
                },
                upsert=True,
            )
        except DuplicateKeyError:
            latest = await self._get_state(revision.resource_id)
            action = decide_stage(revision, latest)
            if action is not StageAction.STAGED:
                return action
            result = await state_collection.update_one(
                _stage_state_filter(revision),
                {
                    "$set": {
                        "staged_content_revision": revision.content_revision,
                        "staged_document_version": revision.document_version,
                    }
                },
            )
        if result.matched_count == 0 and result.upserted_id is None:
            latest = await self._get_state(revision.resource_id)
            action = decide_stage(revision, latest)
            if action is not StageAction.STAGED:
                return action
            raise RuntimeError(f"resource {revision.resource_id} stage changed concurrently")
        return StageAction.STAGED

    async def apply_revision(self, revision: ContentRevision) -> None:
        result = await ResourceIndexStateEntity.get_pymongo_collection().update_one(
            {
                "resource_id": revision.resource_id,
                "staged_content_revision": revision.content_revision,
                "staged_document_version": revision.document_version,
            },
            {
                "$set": {
                    "applied_content_revision": revision.content_revision,
                    "applied_document_version": revision.document_version,
                    "staged_content_revision": None,
                    "staged_document_version": None,
                }
            },
        )
        if result.modified_count == 1:
            return
        state = await self._get_state(revision.resource_id)
        if state is not None and state.applied_content_revision == revision.content_revision:
            return
        raise RuntimeError(f"content revision {revision.content_revision} is no longer staged")

    async def _get_state(self, resource_id: str) -> ResourceIndexState | None:
        entity = await ResourceIndexStateEntity.find_one({"resource_id": resource_id})
        if entity is None:
            return None
        return _to_domain(entity)

    async def delete_other_revisions(
        self,
        *,
        resource_id: str,
        keep_content_revision: str,
    ) -> None:
        revisions = await ContentRevisionEntity.find(
            {
                "resource_id": resource_id,
                "content_revision": {"$ne": keep_content_revision},
            }
        ).to_list()
        revision_ids = [revision.content_revision for revision in revisions]
        if not revision_ids:
            return
        for entity_type in (
            SourcePartEntity,
            SectionEntity,
            ReadingBlockEntity,
            SourceRefEntity,
            ContentRevisionEntity,
        ):
            await entity_type.find(
                {"content_revision": {"$in": revision_ids}}
            ).delete_many()

    async def delete_resources(self, resource_ids: Sequence[str]) -> None:
        ids = list(dict.fromkeys(resource_ids))
        if not ids:
            return
        revisions = await ContentRevisionEntity.find({"resource_id": {"$in": ids}}).to_list()
        revision_ids = [entity.content_revision for entity in revisions]
        await ResourceIndexStateEntity.find({"resource_id": {"$in": ids}}).delete_many()
        if not revision_ids:
            return
        for entity_type in (
            SourcePartEntity,
            SectionEntity,
            ReadingBlockEntity,
            SourceRefEntity,
            ContentRevisionEntity,
        ):
            await entity_type.find({"content_revision": {"$in": revision_ids}}).delete_many()


def split_source_parts(revision: ContentRevision, markdown: str) -> list[SourcePart]:
    if revision.total_length != len(markdown):
        raise ValueError("content revision length does not match markdown")
    return [
        SourcePart(
            resource_id=revision.resource_id,
            content_revision=revision.content_revision,
            part_index=index,
            source_span=SourceSpan(start, min(start + _SOURCE_PART_CHARACTERS, len(markdown))),
            text=markdown[start : start + _SOURCE_PART_CHARACTERS],
        )
        for index, start in enumerate(range(0, len(markdown), _SOURCE_PART_CHARACTERS))
    ]


def _to_domain(record: ResourceIndexStateEntity) -> ResourceIndexState:
    return ResourceIndexState(
        resource_id=record.resource_id,
        staged_content_revision=record.staged_content_revision,
        staged_document_version=record.staged_document_version,
        applied_content_revision=record.applied_content_revision,
        applied_document_version=record.applied_document_version,
    )


def _revision_document(revision: ContentRevision) -> dict[str, object]:
    return {
        "resource_id": revision.resource_id,
        "content_revision": revision.content_revision,
        "document_version": revision.document_version,
        "content_hash": revision.content_hash,
        "index_schema_version": revision.index_schema_version,
        "structure_mode": revision.structure_mode.value,
        "total_length": revision.total_length,
        "pages": [
            {
                "page_index": page.page_index,
                "page_label": page.page_label,
                "start_offset": page.source_span.start_offset,
                "end_offset": page.source_span.end_offset,
            }
            for page in revision.pages
        ],
    }


def _source_part_document(part: SourcePart) -> dict[str, object]:
    return {
        "resource_id": part.resource_id,
        "content_revision": part.content_revision,
        "part_index": part.part_index,
        "start_offset": part.source_span.start_offset,
        "end_offset": part.source_span.end_offset,
        "text": part.text,
    }


def _section_document(
    revision: ContentRevision,
    section: Section,
) -> dict[str, object]:
    return {
        "resource_id": revision.resource_id,
        "content_revision": revision.content_revision,
        "section_id": section.section_id,
        "title": section.title,
        "level": section.level,
        "parent_section_id": section.parent_section_id,
        "ordinal": section.ordinal,
        "section_path": list(section.section_path),
        "preview": section.preview,
        "own_start": section.own_span.start_offset,
        "own_end": section.own_span.end_offset,
        "subtree_end": section.subtree_span.end_offset,
    }


def _reading_block_document(
    revision: ContentRevision,
    block: ReadingBlock,
) -> dict[str, object]:
    return {
        "resource_id": revision.resource_id,
        "content_revision": revision.content_revision,
        "block_id": block.block_id,
        "section_id": block.section_id,
        "ordinal": block.ordinal,
        "raw_text": block.raw_text,
        "source_spans": [_span_document(span) for span in block.source_spans],
        "start_offset": block.source_spans[0].start_offset,
        "end_offset": block.source_spans[-1].end_offset,
        "page_labels": list(block.page_labels),
        "anchor_labels": list(block.anchor_labels),
    }


def _source_ref_document(
    revision: ContentRevision,
    source_ref: SourceRef,
) -> dict[str, object]:
    return {
        "resource_id": revision.resource_id,
        "content_revision": revision.content_revision,
        "ref_id": source_ref.ref_id,
        "chunk_id": source_ref.chunk_id,
        "reading_block_id": source_ref.reading_block_id,
        "section_id": source_ref.section_id,
        "section_path": list(source_ref.section_path),
        "source_spans": [_span_document(span) for span in source_ref.source_spans],
        "page_labels": list(source_ref.page_labels),
        "anchor_labels": list(source_ref.anchor_labels),
    }


def _span_document(span: SourceSpan) -> dict[str, int]:
    return {"start_offset": span.start_offset, "end_offset": span.end_offset}


def _stage_state_filter(revision: ContentRevision) -> dict[str, object]:
    return {
        "resource_id": revision.resource_id,
        "$and": [
            {"$or": [{"applied_document_version": {"$exists": False}}, {"applied_document_version": None}, {"applied_document_version": {"$lte": revision.document_version}}]},
            {"$or": [{"staged_document_version": {"$exists": False}}, {"staged_document_version": None}, {"staged_document_version": {"$lte": revision.document_version}}]},
        ],
    }


def _validate_structure_records(*, revision: ContentRevision, sections: Sequence[Section], reading_blocks: Sequence[ReadingBlock], source_refs: Sequence[SourceRef]) -> None:
    sections_by_id = {section.section_id: section for section in sections}
    blocks_by_id = {block.block_id: block for block in reading_blocks}
    if len(sections_by_id) != len(sections):
        raise ValueError("section identities are not unique")
    if len(blocks_by_id) != len(reading_blocks):
        raise ValueError("reading block identities are not unique")
    if len({ref.ref_id for ref in source_refs}) != len(source_refs):
        raise ValueError("source ref identities are not unique")
    if len({ref.chunk_id for ref in source_refs}) != len(source_refs):
        raise ValueError("source refs contain duplicate chunk identities")
    for section in sections:
        if section.own_span.end_offset > revision.total_length:
            raise ValueError(f"section {section.section_id} exceeds content revision")
        if section.parent_section_id is not None and section.parent_section_id not in sections_by_id:
            raise ValueError(f"section {section.section_id} has no parent")
    for block in reading_blocks:
        section = sections_by_id.get(block.section_id)
        if section is None or not block.source_spans:
            raise ValueError(f"reading block {block.block_id} has invalid ownership")
        if any(span.start_offset < section.own_span.start_offset or span.end_offset > section.own_span.end_offset for span in block.source_spans):
            raise ValueError(f"reading block {block.block_id} exceeds its section")
    for ref in source_refs:
        block = blocks_by_id.get(ref.reading_block_id)
        section = sections_by_id.get(ref.section_id)
        if ref.resource_id != revision.resource_id or ref.content_revision != revision.content_revision or block is None or section is None or block.section_id != section.section_id or ref.section_path != section.section_path or not ref.source_spans:
            raise ValueError(f"source ref {ref.ref_id} has invalid ownership")
