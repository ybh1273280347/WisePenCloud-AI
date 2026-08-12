"""知识导航 HTTP adapter 的严格请求与领域事实响应 schema。"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from rag.application.rag.expand import TraversalDirection
from rag.domain.knowledge_graph import (
    KnowledgeEntityType,
    KnowledgeNodeKind,
    KnowledgeRelationType,
)
from rag.utils.ranking import RankDecision

from .resources import (
    SectionContentResponse,
    SectionFrontierResponse,
    SectionResponse,
    SourceSpanResponse,
)

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class NavigationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: NonEmptyText


class LocateRequest(NavigationRequest):
    semantic_query: NonEmptyText
    lexical_query: NonEmptyText | None = None
    resource_ids: list[NonEmptyText] = Field(default_factory=list, max_length=50)
    max_results: int = Field(default=10, ge=1, le=20)


class ReadSectionsRequest(NavigationRequest):
    state_id: NonEmptyText
    section_ids: list[NonEmptyText] = Field(min_length=1, max_length=12)


class ExpandRequest(NavigationRequest):
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


class LocatedEvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_ref_id: str
    reading_block_id: str
    source_text: str


class LocatedSectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    resource_id: str
    content_revision: str
    section: SectionResponse
    frontier: SectionFrontierResponse
    evidence: list[LocatedEvidenceResponse]


class LocateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    state_id: str
    decision: RankDecision
    sections: list[LocatedSectionResponse]


class ReadSectionsResponse(BaseModel):
    state_id: str
    sections: dict[str, SectionContentResponse]


class KnowledgeNodeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    node_id: str
    kind: KnowledgeNodeKind
    label: str
    entity_type: KnowledgeEntityType | None
    resource_id: str | None


class KnowledgeEdgeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    edge_id: str
    source_node_id: str
    target_node_id: str
    relation_type: KnowledgeRelationType
    predicate: str | None
    evidence_resource_id: str
    source_content_revision: str
    evidence_quotes: list[str]
    evidence_source_ref_ids: list[str]


class KnowledgePathResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    nodes: list[KnowledgeNodeResponse]
    edges: list[KnowledgeEdgeResponse]


class EvidenceSourceResponse(BaseModel):
    content: str
    ref_id: str
    resource_id: str
    content_revision: str
    chunk_id: str
    reading_block_id: str
    section_id: str
    section_path: list[str]
    source_spans: list[SourceSpanResponse]
    page_labels: list[str]
    anchor_labels: list[str]


class ExpandResponse(BaseModel):
    state_id: str
    nodes: list[KnowledgeNodeResponse]
    edges: list[KnowledgeEdgeResponse]
    paths: list[KnowledgePathResponse]
    sources: list[EvidenceSourceResponse]
