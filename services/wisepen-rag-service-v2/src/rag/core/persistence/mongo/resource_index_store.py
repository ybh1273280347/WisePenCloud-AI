"""ResourceIndexStore 的 PyMongo adapter。"""

from collections.abc import Sequence

from pymongo import ASCENDING, IndexModel
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from rag.application.rag.index.revisions import (
    build_content_revision_id,
    decide_stage,
)
from rag.core.persistence.mongo.content_records import (
    read_source_spans,
    reading_block_document,
    revision_document,
    section_document,
    source_part_document,
    source_ref_document,
    to_content_revision,
    to_reading_block,
    to_section,
    to_source_ref,
)
from rag.domain.content_revision import ContentRevision, ResourceIndexState, SourcePart
from rag.domain.document_structure import Section
from rag.domain.reading import ReadingBlock
from rag.domain.repositories import GraphBuildSource, ResourceIndexStore, StageAction
from rag.domain.retrieval import SourceRef
from rag.utils.chunkers import SourceSpan

_SOURCE_PART_CHARACTERS = 1_000_000
_RESOURCE_INDEX_STATES = "wisepen_rag_v2_resource_index_states"
_CONTENT_REVISIONS = "wisepen_rag_v2_content_revisions"
_SOURCE_PARTS = "wisepen_rag_v2_source_parts"
_SECTIONS = "wisepen_rag_v2_sections"
_READING_BLOCKS = "wisepen_rag_v2_reading_blocks"
_SOURCE_REFS = "wisepen_rag_v2_source_refs"


class _BeanieCollection:
    """延迟解析 Beanie Document 的底层 collection，等待 init_beanie 完成。"""

    __slots__ = ("_document",)

    def __init__(self, document: type) -> None:
        self._document = document

    def __getattr__(self, name: str):
        return getattr(self._document.get_pymongo_collection(), name)


class MongoResourceIndexStore(ResourceIndexStore):
    """以 staged/applied CAS 管理资源原文 revision。"""

    __slots__ = (
        "_content_revisions",
        "_reading_blocks",
        "_resource_index_states",
        "_sections",
        "_source_parts",
        "_source_refs",
        "_use_database_collections",
    )

    def __init__(self, database: AsyncDatabase | None = None) -> None:
        from rag.domain.entities import (
            ContentRevisionEntity,
            ReadingBlockEntity,
            ResourceIndexStateEntity,
            SectionEntity,
            SourcePartEntity,
            SourceRefEntity,
        )
        self._use_database_collections = database is not None

        if database is None:
            self._resource_index_states = _BeanieCollection(ResourceIndexStateEntity)
            self._content_revisions = _BeanieCollection(ContentRevisionEntity)
            self._source_parts = _BeanieCollection(SourcePartEntity)
            self._sections = _BeanieCollection(SectionEntity)
            self._reading_blocks = _BeanieCollection(ReadingBlockEntity)
            self._source_refs = _BeanieCollection(SourceRefEntity)
        else:
            self._resource_index_states = database[_RESOURCE_INDEX_STATES]
            self._content_revisions = database[_CONTENT_REVISIONS]
            self._source_parts = database[_SOURCE_PARTS]
            self._sections = database[_SECTIONS]
            self._reading_blocks = database[_READING_BLOCKS]
            self._source_refs = database[_SOURCE_REFS]

    async def initialize(self) -> None:
        if not self._use_database_collections:
            return
        await self._resource_index_states.create_indexes(
            [
                IndexModel(
                    [("resource_id", ASCENDING)],
                    name="idx_rag_v2_resource_index_state_resource",
                    unique=True,
                )
            ]
        )
        await self._content_revisions.create_indexes(
            [
                IndexModel(
                    [("content_revision", ASCENDING)],
                    name="idx_rag_v2_content_revision",
                    unique=True,
                ),
                IndexModel(
                    [("resource_id", ASCENDING), ("document_version", ASCENDING)],
                    name="idx_rag_v2_content_resource_version",
                ),
            ]
        )
        await self._source_parts.create_indexes(
            [
                IndexModel(
                    [("content_revision", ASCENDING), ("part_index", ASCENDING)],
                    name="idx_rag_v2_source_part_revision_order",
                    unique=True,
                ),
                IndexModel(
                    [("resource_id", ASCENDING), ("content_revision", ASCENDING)],
                    name="idx_rag_v2_source_part_resource_revision",
                ),
            ]
        )
        await self._sections.create_indexes(
            [
                IndexModel(
                    [("content_revision", ASCENDING), ("section_id", ASCENDING)],
                    name="idx_rag_v2_section_revision_id",
                    unique=True,
                ),
                IndexModel(
                    [
                        ("content_revision", ASCENDING),
                        ("parent_section_id", ASCENDING),
                        ("ordinal", ASCENDING),
                    ],
                    name="idx_rag_v2_section_children",
                ),
                IndexModel(
                    [
                        ("content_revision", ASCENDING),
                        ("own_start", ASCENDING),
                        ("own_end", ASCENDING),
                    ],
                    name="idx_rag_v2_section_range",
                ),
                IndexModel(
                    [("resource_id", ASCENDING), ("content_revision", ASCENDING)],
                    name="idx_rag_v2_section_resource_revision",
                ),
            ]
        )
        await self._reading_blocks.create_indexes(
            [
                IndexModel(
                    [("content_revision", ASCENDING), ("block_id", ASCENDING)],
                    name="idx_rag_v2_reading_block_revision_id",
                    unique=True,
                ),
                IndexModel(
                    [
                        ("content_revision", ASCENDING),
                        ("section_id", ASCENDING),
                        ("ordinal", ASCENDING),
                    ],
                    name="idx_rag_v2_reading_block_section_order",
                ),
                IndexModel(
                    [
                        ("content_revision", ASCENDING),
                        ("start_offset", ASCENDING),
                        ("end_offset", ASCENDING),
                    ],
                    name="idx_rag_v2_reading_block_range",
                ),
                IndexModel(
                    [("resource_id", ASCENDING), ("content_revision", ASCENDING)],
                    name="idx_rag_v2_reading_block_resource_revision",
                ),
            ]
        )
        await self._source_refs.create_indexes(
            [
                IndexModel(
                    [("content_revision", ASCENDING), ("ref_id", ASCENDING)],
                    name="idx_rag_v2_source_ref_revision_id",
                    unique=True,
                ),
                IndexModel(
                    [("content_revision", ASCENDING), ("chunk_id", ASCENDING)],
                    name="idx_rag_v2_source_ref_revision_chunk",
                    unique=True,
                ),
                IndexModel(
                    [
                        ("content_revision", ASCENDING),
                        ("reading_block_id", ASCENDING),
                    ],
                    name="idx_rag_v2_source_ref_reading_block",
                ),
                IndexModel(
                    [("resource_id", ASCENDING), ("content_revision", ASCENDING)],
                    name="idx_rag_v2_source_ref_resource_revision",
                ),
            ]
        )

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
        state = await self.read_state(revision.resource_id)
        action = decide_stage(revision, state)
        if action is not StageAction.STAGED:
            return action

        await self._content_revisions.replace_one(
            {"content_revision": revision.content_revision},
            revision_document(revision),
            upsert=True,
        )
        await self._source_parts.delete_many(
            {"content_revision": revision.content_revision}
        )
        parts = split_source_parts(revision, markdown)
        if parts:
            await self._source_parts.insert_many(
                [source_part_document(part) for part in parts]
            )
        await self._sections.delete_many(
            {"content_revision": revision.content_revision}
        )
        await self._reading_blocks.delete_many(
            {"content_revision": revision.content_revision}
        )
        await self._source_refs.delete_many(
            {"content_revision": revision.content_revision}
        )
        if sections:
            await self._sections.insert_many(
                [section_document(revision, section) for section in sections]
            )
        if reading_blocks:
            await self._reading_blocks.insert_many(
                [reading_block_document(revision, block) for block in reading_blocks]
            )
        if source_refs:
            await self._source_refs.insert_many(
                [
                    source_ref_document(revision, source_ref)
                    for source_ref in source_refs
                ]
            )

        # staged 指针最后写入；此前任何中断只会留下不可见的 revision 数据。
        state_filter = _stage_state_filter(revision)
        update = {
            "$set": {
                "staged_content_revision": revision.content_revision,
                "staged_document_version": revision.document_version,
            },
            "$setOnInsert": {"resource_id": revision.resource_id},
        }
        try:
            result = await self._resource_index_states.update_one(
                state_filter,
                update,
                upsert=True,
            )
        except DuplicateKeyError:
            # 并发首写可能同时命中 upsert；重新读取后只允许仍然非 stale 的任务重试 CAS。
            latest = await self.read_state(revision.resource_id)
            action = decide_stage(revision, latest)
            if action is not StageAction.STAGED:
                return action
            result = await self._resource_index_states.update_one(
                state_filter,
                update,
                upsert=False,
            )
        if result.matched_count == 0 and result.upserted_id is None:
            latest = await self.read_state(revision.resource_id)
            action = decide_stage(revision, latest)
            if action is not StageAction.STAGED:
                return action
            raise RuntimeError(
                f"resource {revision.resource_id} stage changed concurrently"
            )
        return StageAction.STAGED

    async def apply_revision(self, revision: ContentRevision) -> None:
        result = await self._resource_index_states.update_one(
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

        state = await self.read_state(revision.resource_id)
        if (
            state is not None
            and state.applied_content_revision == revision.content_revision
        ):
            return
        raise RuntimeError(
            f"content revision {revision.content_revision} is no longer staged"
        )

    async def read_state(self, resource_id: str) -> ResourceIndexState | None:
        document = await self._resource_index_states.find_one(
            {"resource_id": resource_id},
            {"_id": False},
        )
        if document is None:
            return None
        return ResourceIndexState(
            resource_id=document["resource_id"],
            staged_content_revision=document.get("staged_content_revision"),
            staged_document_version=document.get("staged_document_version"),
            applied_content_revision=document.get("applied_content_revision"),
            applied_document_version=document.get("applied_document_version"),
        )

    async def read_revision(self, content_revision: str) -> ContentRevision | None:
        document = await self._content_revisions.find_one(
            {"content_revision": content_revision},
            {"_id": False},
        )
        if document is None:
            return None
        return to_content_revision(document)

    async def read_source_text(
        self,
        content_revision: str,
        source_spans: Sequence[SourceSpan],
    ) -> str:
        if not source_spans:
            return ""
        revision = await self.read_revision(content_revision)
        if revision is None:
            raise RuntimeError(f"content revision {content_revision} does not exist")
        if any(
            span.start_offset < 0 or span.end_offset > revision.total_length
            for span in source_spans
        ):
            raise RuntimeError(
                f"content revision {content_revision} span is out of bounds"
            )

        documents = await (
            self._source_parts.find(
                {
                    "content_revision": content_revision,
                    "start_offset": {
                        "$lt": max(span.end_offset for span in source_spans)
                    },
                    "end_offset": {
                        "$gt": min(span.start_offset for span in source_spans)
                    },
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

    async def read_graph_build_source(
        self,
        resource_id: str,
        content_revision: str,
    ) -> GraphBuildSource:
        state = await self.read_state(resource_id)
        if state is None or state.applied_content_revision != content_revision:
            raise RuntimeError(
                f"content revision {content_revision} is not applied for {resource_id}"
            )
        revision = await self.read_revision(content_revision)
        if revision is None or revision.resource_id != resource_id:
            raise RuntimeError(
                f"content revision {content_revision} does not belong to {resource_id}"
            )
        markdown = await self.read_source_text(
            content_revision,
            [SourceSpan(0, revision.total_length)],
        )
        section_documents = await self._sections.find(
            {"resource_id": resource_id, "content_revision": content_revision},
            {"_id": False},
        ).to_list()
        block_documents = await (
            self._reading_blocks.find(
                {"resource_id": resource_id, "content_revision": content_revision},
                {"_id": False},
            )
            .sort([("section_id", ASCENDING), ("ordinal", ASCENDING)])
            .to_list()
        )
        ref_documents = await self._source_refs.find(
            {"resource_id": resource_id, "content_revision": content_revision},
            {"_id": False},
        ).to_list()
        return GraphBuildSource(
            resource_id=resource_id,
            content_revision=content_revision,
            markdown=markdown,
            sections=[to_section(document) for document in section_documents],
            reading_blocks=[
                to_reading_block(document) for document in block_documents
            ],
            source_refs=[to_source_ref(document) for document in ref_documents],
        )

    async def delete_resources(self, resource_ids: Sequence[str]) -> None:
        unique_resource_ids = list(dict.fromkeys(resource_ids))
        if not unique_resource_ids:
            return
        revision_documents = await self._content_revisions.find(
            {"resource_id": {"$in": unique_resource_ids}},
            {"_id": False, "content_revision": True},
        ).to_list()
        content_revisions = [
            str(document["content_revision"]) for document in revision_documents
        ]

        # 先删除可见性指针；后续物理清理失败时所有读取也必须 fail closed。
        await self._resource_index_states.delete_many(
            {"resource_id": {"$in": unique_resource_ids}}
        )
        if not content_revisions:
            return
        revision_filter = {"content_revision": {"$in": content_revisions}}
        for collection in (
            self._source_parts,
            self._sections,
            self._reading_blocks,
            self._source_refs,
            self._content_revisions,
        ):
            await collection.delete_many(revision_filter)


def split_source_parts(
    revision: ContentRevision,
    markdown: str,
) -> list[SourcePart]:
    if revision.total_length != len(markdown):
        raise ValueError("content revision length does not match markdown")
    return [
        SourcePart(
            resource_id=revision.resource_id,
            content_revision=revision.content_revision,
            part_index=part_index,
            source_span=SourceSpan(
                start_offset,
                min(start_offset + _SOURCE_PART_CHARACTERS, len(markdown)),
            ),
            text=markdown[start_offset : start_offset + _SOURCE_PART_CHARACTERS],
        )
        for part_index, start_offset in enumerate(
            range(0, len(markdown), _SOURCE_PART_CHARACTERS)
        )
    ]


def _stage_state_filter(revision: ContentRevision) -> dict[str, object]:
    return {
        "resource_id": revision.resource_id,
        "$and": [
            {
                "$or": [
                    {"applied_document_version": {"$exists": False}},
                    {"applied_document_version": None},
                    {"applied_document_version": {"$lte": revision.document_version}},
                ]
            },
            {
                "$or": [
                    {"staged_document_version": {"$exists": False}},
                    {"staged_document_version": None},
                    {"staged_document_version": {"$lte": revision.document_version}},
                ]
            },
        ],
    }


def _validate_structure_records(
    *,
    revision: ContentRevision,
    sections: Sequence[Section],
    reading_blocks: Sequence[ReadingBlock],
    source_refs: Sequence[SourceRef],
) -> None:
    sections_by_id = {section.section_id: section for section in sections}
    if len(sections_by_id) != len(sections):
        raise ValueError("section identities are not unique")
    blocks_by_id = {block.block_id: block for block in reading_blocks}
    if len(blocks_by_id) != len(reading_blocks):
        raise ValueError("reading block identities are not unique")
    if len({source_ref.ref_id for source_ref in source_refs}) != len(source_refs):
        raise ValueError("source ref identities are not unique")
    if len({source_ref.chunk_id for source_ref in source_refs}) != len(source_refs):
        raise ValueError("source refs contain duplicate chunk identities")

    for section in sections:
        if section.own_span.end_offset > revision.total_length:
            raise ValueError(f"section {section.section_id} exceeds content revision")
        if (
            section.parent_section_id is not None
            and section.parent_section_id not in sections_by_id
        ):
            raise ValueError(f"section {section.section_id} has no parent")
    for block in reading_blocks:
        section = sections_by_id.get(block.section_id)
        if section is None:
            raise ValueError(f"reading block {block.block_id} has no section")
        if not block.source_spans:
            raise ValueError(f"reading block {block.block_id} has no source span")
        if any(
            span.start_offset < section.own_span.start_offset
            or span.end_offset > section.own_span.end_offset
            for span in block.source_spans
        ):
            raise ValueError(f"reading block {block.block_id} exceeds its section")
    for source_ref in source_refs:
        if source_ref.resource_id != revision.resource_id:
            raise ValueError(f"source ref {source_ref.ref_id} has invalid resource")
        if source_ref.content_revision != revision.content_revision:
            raise ValueError(f"source ref {source_ref.ref_id} has invalid revision")
        block = blocks_by_id.get(source_ref.reading_block_id)
        section = sections_by_id.get(source_ref.section_id)
        if block is None or section is None or block.section_id != section.section_id:
            raise ValueError(f"source ref {source_ref.ref_id} has invalid ownership")
        if source_ref.section_path != section.section_path:
            raise ValueError(f"source ref {source_ref.ref_id} has invalid section path")
        if not source_ref.source_spans:
            raise ValueError(f"source ref {source_ref.ref_id} has no source span")
