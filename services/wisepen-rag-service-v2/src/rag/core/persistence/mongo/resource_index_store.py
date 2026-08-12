"""ResourceIndexStore 的 PyMongo adapter。"""

from collections.abc import Sequence

from pymongo import ASCENDING, IndexModel
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from rag.application.rag.index.resource_index_store import (
    ResourceIndexStore,
    StageAction,
    build_content_revision_id,
    decide_stage,
)
from rag.domain.content_revision import ContentRevision, ResourceIndexState, SourcePart
from rag.domain.document_structure import PageRange, StructureMode
from rag.utils.chunkers import SourceSpan

_SOURCE_PART_CHARACTERS = 1_000_000
_RESOURCE_INDEX_STATES = "wisepen_rag_v2_resource_index_states"
_CONTENT_REVISIONS = "wisepen_rag_v2_content_revisions"
_SOURCE_PARTS = "wisepen_rag_v2_source_parts"


class MongoResourceIndexStore(ResourceIndexStore):
    """以 staged/applied CAS 管理资源原文 revision。"""

    __slots__ = ("_content_revisions", "_resource_index_states", "_source_parts")

    def __init__(self, database: AsyncDatabase) -> None:
        self._resource_index_states = database[_RESOURCE_INDEX_STATES]
        self._content_revisions = database[_CONTENT_REVISIONS]
        self._source_parts = database[_SOURCE_PARTS]

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

    async def stage_revision(
        self,
        revision: ContentRevision,
        markdown: str,
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
