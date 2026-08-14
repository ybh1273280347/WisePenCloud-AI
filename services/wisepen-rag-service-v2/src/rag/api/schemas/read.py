"""READ endpoints 的请求与响应 schema。"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from rag.application.rag.read.content import PageContentView, SectionContentView
from rag.application.rag.read.outline import DocumentOutlineNode

NonEmptyText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1)
]


class ResourceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: NonEmptyText


class PageContentRequest(ResourceRequest):
    page_labels: list[NonEmptyText] = Field(min_length=1, max_length=20)


class SectionContentRequest(ResourceRequest):
    section_ids: list[NonEmptyText] = Field(min_length=1, max_length=20)


PageContentResponse = dict[str, PageContentView]
SectionContentResponse = dict[str, SectionContentView]


class DocumentOutlineResponse(BaseModel):
    resource_id: str
    document_version: int
    content_revision: str
    total_length: int
    outline: list[DocumentOutlineNode]
