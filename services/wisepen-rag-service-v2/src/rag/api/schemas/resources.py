"""确定性资源 READ endpoints 的请求与响应 schema。"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ResourceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: NonEmptyText


class PageContentRequest(ResourceRequest):
    page_labels: list[NonEmptyText] = Field(min_length=1, max_length=20)


class SectionContentRequest(ResourceRequest):
    section_ids: list[NonEmptyText] = Field(min_length=1, max_length=20)


class SourceSpanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    start_offset: int
    end_offset: int


class PageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    page_index: int
    page_label: str
    source_span: SourceSpanResponse


class SectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    section_id: str
    title: str
    level: int
    parent_section_id: str | None
    ordinal: int
    section_path: list[str]
    own_span: SourceSpanResponse
    subtree_span: SourceSpanResponse
    preview: str


class DocumentStructureResponse(BaseModel):
    resource_id: str
    document_version: int
    content_revision: str
    structure_mode: str
    total_length: int
    pages: list[PageResponse]
    sections: list[SectionResponse]


class ContentWindowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    text: str
    source_span: SourceSpanResponse
    source_spans: list[SourceSpanResponse]
    page_labels: list[str]
    section_ids: list[str]
    anchor_labels: list[str]


class ReadingBlockResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    block_id: str
    section_id: str
    ordinal: int
    raw_text: str
    source_spans: list[SourceSpanResponse]
    page_labels: list[str]
    anchor_labels: list[str]


class SectionFrontierResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    parent: SectionResponse | None
    previous: SectionResponse | None
    next: SectionResponse | None
    children: list[SectionResponse]


class SectionContentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    section: SectionResponse
    reading_blocks: list[ReadingBlockResponse]
    frontier: SectionFrontierResponse
