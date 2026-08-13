"""EXPAND endpoint 的请求与响应 schema。"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from rag.application.rag.expand import TraversalDirection
from rag.domain.models.structure import Section
from rag.domain.models.evidence import EvidenceRecord
from rag.domain.models.graph import TraversedEdge, TraversedPath
from rag.domain.models.graph import KnowledgeNode, KnowledgeRelationType
from rag.domain.models.content import SectionFrontier
from rag.domain.models.content import ReadingBlock

NonEmptyText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]


class DiscoveredSectionExpandRequest(BaseModel):
    """只允许展开 navigation state 中已发现的 Section。"""

    model_config = ConfigDict(extra="forbid")

    session_id: NonEmptyText
    state_id: NonEmptyText
    section_ids: list[NonEmptyText] = Field(min_length=1, max_length=12)


class SectionView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    resource_id: str
    content_revision: str
    section: Section
    reading_blocks: list[ReadingBlock]
    frontier: SectionFrontier
    evidence: list[EvidenceRecord] = Field(default_factory=list)


class DiscoveredSectionExpandResponse(BaseModel):
    state_id: str
    sections: list[SectionView]


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


class GraphExpandResponse(BaseModel):
    state_id: str
    nodes: list[KnowledgeNode]
    edges: list[TraversedEdge]
    paths: list[TraversedPath]
    sources: list[SectionView]
