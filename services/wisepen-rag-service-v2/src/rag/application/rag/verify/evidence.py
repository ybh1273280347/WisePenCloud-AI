"""VERIFY 用例：校验候选检索块并返回 applied 原文证据。"""

from collections.abc import Sequence

from rag.domain.evidence import (
    EvidenceCandidate,
    EvidenceCorruptError,
    EvidenceNotFoundError,
    EvidenceRecord,
    EvidenceRevisionError,
)
from rag.domain.repositories.evidence_reader import EvidenceReader


class EvidenceVerifier:
    """按 SourceRef 身份回源，并逐项校验候选字段归属。"""

    __slots__ = ("_reader",)

    def __init__(self, *, reader: EvidenceReader) -> None:
        self._reader = reader

    async def verify(
        self,
        candidates: Sequence[EvidenceCandidate],
    ) -> list[EvidenceRecord]:
        if not candidates:
            return []

        resource_ids = {candidate.resource_id for candidate in candidates}
        revisions = {candidate.content_revision for candidate in candidates}
        if len(resource_ids) != 1 or len(revisions) != 1:
            raise EvidenceRevisionError(
                "evidence candidates must share one resource revision"
            )

        resource_id = next(iter(resource_ids))
        content_revision = next(iter(revisions))
        records = await self._reader.read_applied_evidence(
            resource_id,
            content_revision,
            list(dict.fromkeys(candidate.source_ref_id for candidate in candidates)),
        )
        if records is None:
            raise EvidenceNotFoundError(resource_id)

        verified: list[EvidenceRecord] = []
        for candidate in candidates:
            record = records.get(candidate.source_ref_id)
            if record is None:
                raise EvidenceNotFoundError(candidate.source_ref_id)
            self._verify_candidate(candidate, record)
            verified.append(record)
        return verified

    async def verify_refs(
        self,
        *,
        resource_id: str,
        content_revision: str,
        source_ref_ids: Sequence[str],
        quotes: Sequence[str],
    ) -> list[EvidenceRecord]:
        """核验图关系引用仍属于当前 applied revision 的权威原文。"""
        ids = list(dict.fromkeys(source_ref_ids))
        records = await self._reader.read_applied_evidence(
            resource_id,
            content_revision,
            ids,
        )
        if records is None:
            raise EvidenceNotFoundError(resource_id)
        if set(records) != set(ids):
            missing = next(ref_id for ref_id in ids if ref_id not in records)
            raise EvidenceNotFoundError(missing)

        ordered = [records[ref_id] for ref_id in ids]
        for quote in dict.fromkeys(quotes):
            if not quote or not any(quote in record.source_text for record in ordered):
                raise EvidenceCorruptError(
                    f"knowledge evidence quote is absent from {resource_id}"
                )
        return ordered

    @staticmethod
    def _verify_candidate(
        candidate: EvidenceCandidate,
        record: EvidenceRecord,
    ) -> None:
        source_ref = record.source_ref
        chunk = candidate.chunk
        if source_ref.resource_id != candidate.resource_id:
            raise EvidenceRevisionError(
                f"source ref {source_ref.ref_id} has invalid resource"
            )
        if source_ref.content_revision != candidate.content_revision:
            raise EvidenceRevisionError(
                f"source ref {source_ref.ref_id} has invalid revision"
            )
        if source_ref.ref_id != candidate.source_ref_id:
            raise EvidenceCorruptError(
                "evidence reader returned a mismatched source ref"
            )
        if chunk.chunk_id != source_ref.chunk_id:
            raise EvidenceCorruptError(
                f"chunk {chunk.chunk_id} does not match source ref"
            )
        if chunk.reading_block_id != source_ref.reading_block_id:
            raise EvidenceCorruptError(
                f"chunk {chunk.chunk_id} has invalid reading block"
            )
        if chunk.section_id != source_ref.section_id:
            raise EvidenceCorruptError(
                f"chunk {chunk.chunk_id} has invalid section"
            )
        if chunk.section_path != source_ref.section_path:
            raise EvidenceCorruptError(
                f"chunk {chunk.chunk_id} has invalid section path"
            )
        if chunk.source_spans != source_ref.source_spans:
            raise EvidenceCorruptError(
                f"chunk {chunk.chunk_id} has invalid source spans"
            )
        if chunk.page_labels != source_ref.page_labels:
            raise EvidenceCorruptError(
                f"chunk {chunk.chunk_id} has invalid page labels"
            )
        if chunk.anchor_labels != source_ref.anchor_labels:
            raise EvidenceCorruptError(
                f"chunk {chunk.chunk_id} has invalid anchor labels"
            )
        if record.reading_block.block_id != source_ref.reading_block_id:
            raise EvidenceCorruptError(
                f"source ref {source_ref.ref_id} has invalid block record"
            )
        if record.reading_block.section_id != source_ref.section_id:
            raise EvidenceCorruptError(
                f"source ref {source_ref.ref_id} has invalid block owner"
            )
        if record.section.section_id != source_ref.section_id:
            raise EvidenceCorruptError(
                f"source ref {source_ref.ref_id} has invalid section record"
            )
        if chunk.raw_text != record.source_text:
            raise EvidenceCorruptError(
                f"chunk {chunk.chunk_id} does not match authoritative text"
            )
