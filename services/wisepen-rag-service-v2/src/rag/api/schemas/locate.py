"""LOCATE endpoint 的请求与响应 schema。"""
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from rag.application.rag.locate import LocatedSection
from rag.domain.knowledge_graph import KnowledgeNode
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


class CandidateLocateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    state_id: str
    decision: RankDecision
    nodes: list[KnowledgeNode]
    sections: list[LocatedSection]
