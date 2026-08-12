"""VERIFY 使用的权威证据事实和候选输入。"""

from dataclasses import dataclass

from rag.domain.content_revision import ContentRevision
from rag.domain.document_structure import Section
from rag.domain.reading import ReadingBlock
from rag.domain.retrieval import RetrievalChunk, SourceRef


class EvidenceNotFoundError(RuntimeError):
    """请求的 applied 内容或证据身份不存在。"""


class EvidenceRevisionError(RuntimeError):
    """请求 revision 不是资源当前 applied revision。"""


class EvidenceCorruptError(RuntimeError):
    """权威原文、SourceRef 或结构记录不满足一致性约束。"""


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
