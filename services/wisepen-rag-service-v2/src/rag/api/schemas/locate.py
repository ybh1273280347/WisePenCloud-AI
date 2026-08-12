"""LOCATE endpoint 的请求与响应 schema。"""
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from rag.domain.document_structure import Section
from rag.domain.knowledge_graph import KnowledgeNode
from rag.domain.read_content import SectionFrontier
from rag.utils.ranking import RankDecision

NonEmptyText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1)
]


class CandidateLocateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: NonEmptyText
    semantic_query: NonEmptyText
    lexical_query: NonEmptyText | None = None
    resource_ids: list[NonEmptyText] = Field(default_factory=list, max_length=50)
    max_results: int = Field(default=10, ge=1, le=20)


class LocatedEvidence(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_ref_id: str
    reading_block_id: str
    source_text: str


class LocatedSection(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    resource_id: str
    content_revision: str
    section: Section
    frontier: SectionFrontier
    evidence: list[LocatedEvidence]


class CandidateLocateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    state_id: str
    decision: RankDecision
    nodes: list[KnowledgeNode]
    sections: list[LocatedSection]
