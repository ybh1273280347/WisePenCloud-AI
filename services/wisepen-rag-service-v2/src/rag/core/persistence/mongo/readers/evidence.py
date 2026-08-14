"""EvidenceReader 的 Beanie adapter。"""

from collections.abc import Sequence
from hashlib import sha256

from rag.application.rag.navigate import EvidenceCorruptError, EvidenceRevisionError
from rag.domain.entities import ReadingBlockEntity, SectionEntity, SourceRefEntity
from rag.domain.models.content import ReadingBlock
from rag.domain.models.evidence import EvidenceRecord
from rag.domain.models.retrieval import SourceRef
from rag.domain.models.structure import Section
from rag.domain.repositories.mongo.readers.applied_revision import AppliedRevisionReader
from rag.domain.repositories.mongo.readers.evidence import EvidenceReader
from rag.domain.repositories.mongo.readers.source_parts import SourcePartReader
from rag.utils.chunkers import SourceSpan

from ..text_assembler import assemble_source_text


class MongoEvidenceReader(EvidenceReader):
    """从 applied revision 读取 SourceRef 的完整权威证据。"""

    def __init__(
        self,
        *,
        revisions: AppliedRevisionReader,
        source_parts: SourcePartReader,
    ) -> None:
        self._revisions = revisions
        self._source_parts = source_parts

    async def read_applied_evidence(
        self,
        resource_id: str,
        content_revision: str,
        source_ref_ids: Sequence[str],
    ) -> dict[str, EvidenceRecord] | None:
        revision = await self._revisions.get_applied_revision(resource_id)
        if revision is None:
            return None
        if revision.content_revision != content_revision:
            raise EvidenceRevisionError(
                f"content revision {content_revision} is not applied for {resource_id}"
            )

        full_span = SourceSpan(0, revision.total_length)
        parts = await self._source_parts.get_parts(content_revision, [full_span])
        full_text = assemble_source_text(parts, [full_span])

        if sha256(full_text.encode("utf-8")).hexdigest() != revision.content_hash:
            raise EvidenceCorruptError(
                f"content revision {content_revision} hash does not match source parts"
            )

        requested_ids = list(dict.fromkeys(source_ref_ids))
        if not requested_ids:
            return {}

        ref_entities = await SourceRefEntity.find(
            {
                "resource_id": resource_id,
                "content_revision": content_revision,
                "ref_id": {"$in": requested_ids},
            }
        ).to_list()
        refs = [_to_source_ref(entity) for entity in ref_entities]

        block_ids = {ref.reading_block_id for ref in refs}
        blocks = await ReadingBlockEntity.find(
            {
                "resource_id": resource_id,
                "content_revision": content_revision,
                "block_id": {"$in": list(block_ids)},
            }
        ).to_list()

        section_ids = {ref.section_id for ref in refs}
        sections = await SectionEntity.find(
            {
                "resource_id": resource_id,
                "content_revision": content_revision,
                "section_id": {"$in": list(section_ids)},
            }
        ).to_list()

        blocks_by_id = {block.block_id: _to_reading_block(block) for block in blocks}
        sections_by_id = {
            section.section_id: _to_section(section) for section in sections
        }

        records: dict[str, EvidenceRecord] = {}
        for source_ref in refs:
            block = blocks_by_id.get(source_ref.reading_block_id)
            section = sections_by_id.get(source_ref.section_id)
            if block is None or section is None:
                raise EvidenceCorruptError(
                    f"source ref {source_ref.ref_id} has missing ownership records"
                )
            records[source_ref.ref_id] = EvidenceRecord(
                revision=revision,
                source_ref=source_ref,
                reading_block=block,
                section=section,
                source_text=assemble_source_text(parts, source_ref.source_spans),
            )

        return records


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
        content_spans=[SourceSpan(span.start_offset, span.end_offset) for span in record.content_spans],
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


def _to_source_ref(record: SourceRefEntity) -> SourceRef:
    return SourceRef(
        ref_id=record.ref_id,
        resource_id=record.resource_id,
        content_revision=record.content_revision,
        chunk_id=record.chunk_id,
        reading_block_id=record.reading_block_id,
        section_id=record.section_id,
        section_path=list(record.section_path),
        source_spans=[
            SourceSpan(span.start_offset, span.end_offset)
            for span in record.source_spans
        ],
        page_labels=list(record.page_labels),
        anchor_labels=list(record.anchor_labels),
    )
