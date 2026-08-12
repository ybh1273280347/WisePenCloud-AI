"""READ endpoints 的请求与响应 schema。"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from rag.domain.models.structure import PageRange, Section

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


class DocumentStructureResponse(BaseModel):
    resource_id: str
    document_version: int
    content_revision: str
    structure_mode: str
    total_length: int
    pages: list[PageRange]
    sections: list[Section]
