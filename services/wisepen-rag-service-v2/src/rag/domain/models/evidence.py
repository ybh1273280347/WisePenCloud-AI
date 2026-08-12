"""VERIFY、LOCATE 和图谱回源共享的证据领域模型。"""

from dataclasses import dataclass

from rag.domain.models.content import ContentRevision, ReadingBlock
from rag.domain.models.retrieval import RetrievalChunk, SourceRef
from rag.domain.models.structure import Section


@dataclass(slots=True)
class EvidenceCandidate:
    resource_id: str
    content_revision: str
    source_ref_id: str
    chunk: RetrievalChunk


@dataclass(slots=True)
class EvidenceRecord:
    revision: ContentRevision
    source_ref: SourceRef
    reading_block: ReadingBlock
    section: Section
    source_text: str
