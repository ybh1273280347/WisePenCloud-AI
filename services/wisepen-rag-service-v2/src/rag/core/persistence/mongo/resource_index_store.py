"""ResourceIndexStore 的 PyMongo adapter。"""

from collections.abc import Sequence

from pymongo import ASCENDING, IndexModel
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from rag.application.rag.index.resource_index_store import (
    GraphBuildSource,
    ResourceIndexStore,
    StageAction,
    build_content_revision_id,
    decide_stage,
)
from rag.domain.content_revision import ContentRevision, ResourceIndexState, SourcePart
from rag.domain.document_structure import PageRange, Section, StructureMode
from rag.domain.reading import ReadingBlock
from rag.domain.retrieval import SourceRef
from rag.utils.chunkers import SourceSpan

_SOURCE_PART_CHARACTERS = 1_000_000
_RESOURCE_INDEX_STATES = "wisepen_rag_v2_resource_index_states"
_CONTENT_REVISIONS = "wisepen_rag_v2_content_revisions"
_SOURCE_PARTS = "wisepen_rag_v2_source_parts"
_SECTIONS = "wisepen_rag_v2_sections"
_READING_BLOCKS = "wisepen_rag_v2_reading_blocks"
_SOURCE_REFS = "wisepen_rag_v2_source_refs"


class MongoResourceIndexStore(ResourceIndexStore):
    """以 staged/applied CAS 管理资源原文 revision。"""

    __slots__ = (
        "_content_revisions",
        "_reading_blocks",
        "_resource_index_states",
        "_sections",
        "_source_parts",
        "_source_refs",
    )

    def __init__(self, database: AsyncDatabase) -> None:
        self._resource_index_states = database[_RESOURCE_INDEX_STATES]
        self._content_revisions = database[_CONTENT_REVISIONS]
        self._source_parts = database[_SOURCE_PARTS]
        self._sections = database[_SECTIONS]
        self._reading_blocks = database[_READING_BLOCKS]
        self._source_refs = database[_SOURCE_REFS]

    async def initialize(self) -> None:
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
            _revision_document(revision),
            upsert=True,
        )
        await self._source_parts.delete_many(
            {"content_revision": revision.content_revision}
        )
        parts = split_source_parts(revision, markdown)
        if parts:
            await self._source_parts.insert_many(
                [_source_part_document(part) for part in parts]
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
                [_section_document(revision, section) for section in sections]
            )
        if reading_blocks:
            await self._reading_blocks.insert_many(
                [_reading_block_document(revision, block) for block in reading_blocks]
            )
        if source_refs:
            await self._source_refs.insert_many(
                [
                    _source_ref_document(revision, source_ref)
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
        return _to_content_revision(document)

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
        return _read_source_spans(
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
            sections=[_to_section(document) for document in section_documents],
            reading_blocks=[
                _to_reading_block(document) for document in block_documents
            ],
            source_refs=[_to_source_ref(document) for document in ref_documents],
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
    return {
        "start_offset": span.start_offset,
        "end_offset": span.end_offset,
    }


def _to_content_revision(document: dict[str, object]) -> ContentRevision:
    return ContentRevision(
        resource_id=str(document["resource_id"]),
        content_revision=str(document["content_revision"]),
        document_version=int(document["document_version"]),
        content_hash=str(document["content_hash"]),
        index_schema_version=str(document["index_schema_version"]),
        structure_mode=StructureMode(str(document["structure_mode"])),
        total_length=int(document["total_length"]),
        pages=[
            PageRange(
                page_index=int(page["page_index"]),
                page_label=str(page["page_label"]),
                source_span=SourceSpan(
                    int(page["start_offset"]),
                    int(page["end_offset"]),
                ),
            )
            for page in document.get("pages", [])
        ],
    )


def _to_section(document: dict[str, object]) -> Section:
    return Section(
        section_id=str(document["section_id"]),
        title=str(document["title"]),
        level=int(document["level"]),
        parent_section_id=(
            str(document["parent_section_id"])
            if document.get("parent_section_id") is not None
            else None
        ),
        ordinal=int(document["ordinal"]),
        section_path=[str(value) for value in document.get("section_path", [])],
        own_span=SourceSpan(
            int(document["own_start"]),
            int(document["own_end"]),
        ),
        subtree_span=SourceSpan(
            int(document["own_start"]),
            int(document["subtree_end"]),
        ),
        preview=str(document.get("preview", "")),
    )


def _to_reading_block(document: dict[str, object]) -> ReadingBlock:
    return ReadingBlock(
        block_id=str(document["block_id"]),
        section_id=str(document["section_id"]),
        ordinal=int(document["ordinal"]),
        raw_text=str(document["raw_text"]),
        source_spans=_to_source_spans(document.get("source_spans", [])),
        page_labels=[str(value) for value in document.get("page_labels", [])],
        anchor_labels=[str(value) for value in document.get("anchor_labels", [])],
    )


def _to_source_ref(document: dict[str, object]) -> SourceRef:
    return SourceRef(
        ref_id=str(document["ref_id"]),
        resource_id=str(document["resource_id"]),
        content_revision=str(document["content_revision"]),
        chunk_id=str(document["chunk_id"]),
        reading_block_id=str(document["reading_block_id"]),
        section_id=str(document["section_id"]),
        section_path=[str(value) for value in document.get("section_path", [])],
        source_spans=_to_source_spans(document.get("source_spans", [])),
        page_labels=[str(value) for value in document.get("page_labels", [])],
        anchor_labels=[str(value) for value in document.get("anchor_labels", [])],
    )


def _to_source_spans(documents: object) -> list[SourceSpan]:
    if not isinstance(documents, list):
        raise RuntimeError("stored source spans must be a list")
    return [
        SourceSpan(
            int(document["start_offset"]),
            int(document["end_offset"]),
        )
        for document in documents
    ]


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


def _read_source_spans(
    *,
    content_revision: str,
    documents: list[dict[str, object]],
    source_spans: Sequence[SourceSpan],
) -> str:
    fragments: list[str] = []
    for span in source_spans:
        cursor = span.start_offset
        span_fragments: list[str] = []
        for document in documents:
            start_offset = int(document["start_offset"])
            end_offset = int(document["end_offset"])
            text = str(document["text"])
            if end_offset - start_offset != len(text):
                raise RuntimeError(
                    f"content revision {content_revision} has an invalid source part"
                )
            if end_offset <= cursor:
                continue
            if start_offset >= span.end_offset:
                break
            if start_offset > cursor:
                raise RuntimeError(
                    f"content revision {content_revision} source parts have a gap"
                )

            fragment_end = min(end_offset, span.end_offset)
            span_fragments.append(
                text[cursor - start_offset : fragment_end - start_offset]
            )
            cursor = fragment_end
            if cursor == span.end_offset:
                break
        if cursor != span.end_offset:
            raise RuntimeError(
                f"content revision {content_revision} source parts do not cover span"
            )
        fragments.append("".join(span_fragments))
    return "\n\n".join(fragments)
