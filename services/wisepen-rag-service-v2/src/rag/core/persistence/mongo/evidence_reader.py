"""EvidenceReader 的 Beanie adapter。"""

from collections.abc import Sequence
from hashlib import sha256

from rag.core.persistence.mongo.content_records import (
    read_source_spans,
    to_content_revision,
    to_reading_block,
    to_section,
    to_source_ref,
)
from rag.domain.entities import (
    ContentRevisionEntity,
    ReadingBlockEntity,
    ResourceIndexStateEntity,
    SectionEntity,
    SourcePartEntity,
    SourceRefEntity,
)
from rag.domain.evidence import (
    EvidenceCorruptError,
    EvidenceRecord,
    EvidenceRevisionError,
)
from rag.domain.repositories.evidence_reader import EvidenceReader
from rag.utils.chunkers import SourceSpan


class MongoEvidenceReader(EvidenceReader):
    """从 applied revision 读取 SourceRef 的完整权威证据。"""

    async def read_applied_evidence(
        self,
        resource_id: str,
        content_revision: str,
        source_ref_ids: Sequence[str],
    ) -> dict[str, EvidenceRecord] | None:
        state = await ResourceIndexStateEntity.find_one({"resource_id": resource_id})
        if state is None or state.applied_content_revision is None:
            return None
        if state.applied_content_revision != content_revision:
            raise EvidenceRevisionError(
                f"content revision {content_revision} is not applied for {resource_id}"
            )
        revision_entity = await ContentRevisionEntity.find_one(
            {"resource_id": resource_id, "content_revision": content_revision}
        )
        if revision_entity is None:
            raise EvidenceCorruptError(f"resource {resource_id} applied revision is missing")
        revision = to_content_revision(revision_entity.model_dump())
        parts = await SourcePartEntity.find({"content_revision": content_revision}).sort("+part_index").to_list()
        documents = [part.model_dump() for part in parts]
        full_text = read_source_spans(
            content_revision=content_revision,
            documents=documents,
            source_spans=[SourceSpan(0, revision.total_length)],
        )
        if sha256(full_text.encode("utf-8")).hexdigest() != revision.content_hash:
            raise EvidenceCorruptError(f"content revision {content_revision} hash does not match source parts")
        requested_ids = list(dict.fromkeys(source_ref_ids))
        if not requested_ids:
            return {}
        ref_entities = await SourceRefEntity.find(
            {"resource_id": resource_id, "content_revision": content_revision, "ref_id": {"$in": requested_ids}}
        ).to_list()
        refs = [to_source_ref(entity.model_dump()) for entity in ref_entities]
        blocks = await ReadingBlockEntity.find(
            {"resource_id": resource_id, "content_revision": content_revision, "block_id": {"$in": list({ref.reading_block_id for ref in refs})}}
        ).to_list()
        sections = await SectionEntity.find(
            {"resource_id": resource_id, "content_revision": content_revision, "section_id": {"$in": list({ref.section_id for ref in refs})}}
        ).to_list()
        blocks_by_id = {block.block_id: to_reading_block(block.model_dump()) for block in blocks}
        sections_by_id = {section.section_id: to_section(section.model_dump()) for section in sections}
        records: dict[str, EvidenceRecord] = {}
        for source_ref in refs:
            block = blocks_by_id.get(source_ref.reading_block_id)
            section = sections_by_id.get(source_ref.section_id)
            if block is None or section is None:
                raise EvidenceCorruptError(f"source ref {source_ref.ref_id} has missing ownership records")
            records[source_ref.ref_id] = EvidenceRecord(
                revision=revision,
                source_ref=source_ref,
                reading_block=block,
                section=section,
                source_text=read_source_spans(
                    content_revision=content_revision,
                    documents=documents,
                    source_spans=source_ref.source_spans,
                ),
            )
        return records
