"""EXPAND endpoint 的请求与响应 schema。"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from rag.application.rag.expand import TraversalDirection
from rag.application.rag.expand.ports import TraversedEdge, TraversedPath
from rag.application.rag.read import SectionFrontier
from rag.domain.document_structure import Section
from rag.domain.evidence import EvidenceRecord
from rag.domain.knowledge_graph import KnowledgeNode, KnowledgeRelationType
from rag.domain.reading import ReadingBlock
from rag.utils.chunkers import SourceSpan

NonEmptyText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]


class SectionExpandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: NonEmptyText
    state_id: NonEmptyText
    section_ids: list[NonEmptyText] = Field(min_length=1, max_length=12)


class SectionExpandResponse(BaseModel):
    state_id: str
    sections: list["SectionViewResponse"]


class SectionViewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    resource_id: str
    content_revision: str
    section: Section
    reading_blocks: list[ReadingBlock]
    frontier: SectionFrontier
    evidence: list[EvidenceRecord] = Field(default_factory=list)


class GraphExpandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: NonEmptyText
    state_id: NonEmptyText
    seed_node_ids: list[NonEmptyText] = Field(min_length=1, max_length=16)
    relation_types: list[KnowledgeRelationType] = Field(
        default_factory=list,
        max_length=16,
    )
    direction: TraversalDirection = TraversalDirection.BOTH
    max_depth: int = Field(default=1, ge=1, le=2)
    max_results: int = Field(default=10, ge=1, le=20)
    query: NonEmptyText | None = None


class EvidenceSource(BaseModel):
    content: str
    ref_id: str
    resource_id: str
    content_revision: str
    chunk_id: str
    reading_block_id: str
    section_id: str
    section_path: list[str]
    source_spans: list[SourceSpan]
    page_labels: list[str]
    anchor_labels: list[str]


class GraphExpandResponse(BaseModel):
    state_id: str
    nodes: list[KnowledgeNode]
    edges: list[TraversedEdge]
    paths: list[TraversedPath]
    sources: list[EvidenceSource]
