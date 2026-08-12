import pytest
from common.core.domain import GroupRoleType
from common.core.exceptions import ServiceException
from common.security import SecurityContextHolder
from pydantic import ValidationError

from rag.api.endpoints.resources import (
    document_structure,
    page_content,
    section_content,
)
from rag.api.router import api_router
from rag.api.schemas import (
    PageContentRequest,
    ResourceRequest,
    SectionContentRequest,
)
from rag.application.rag.read import ContentNotFoundError
from rag.domain.content_revision import ContentRevision
from rag.domain.document_structure import PageRange, Section, StructureMode
from rag.domain.error_codes import RagErrorCode
from rag.domain.read_content import (
    ContentWindow,
    DocumentStructureResult,
    SectionContent,
    SectionFrontier,
)
from rag.utils.chunkers import SourceSpan


class _StructureReader:
    def __init__(self, *, missing=False) -> None:
        self.missing = missing
        self.scope = None

    async def get(self, *, resource_id, permission_scope):
        self.scope = permission_scope
        if self.missing:
            raise ContentNotFoundError(resource_id)
        return DocumentStructureResult(
            revision=ContentRevision(
                resource_id=resource_id,
                content_revision="revision-1",
                document_version=3,
                content_hash="hash",
                index_schema_version="v1",
                structure_mode=StructureMode.SECTIONED,
                total_length=12,
                pages=[PageRange(0, "1", SourceSpan(0, 12))],
            ),
            sections=[_section()],
        )


class _ContentReader:
    def __init__(self, *, missing=False) -> None:
        self.missing = missing

    async def get_pages(self, *, resource_id, page_labels, permission_scope):
        if self.missing:
            raise ContentNotFoundError(resource_id)
        return {
            "1": ContentWindow(
                text="正文",
                source_span=SourceSpan(0, 2),
                source_spans=[SourceSpan(0, 2)],
                page_labels=["1"],
            )
        }

    async def get_sections(self, *, resource_id, section_ids, permission_scope):
        if self.missing:
            raise ContentNotFoundError(resource_id)
        section = _section()
        return {
            section.section_id: SectionContent(
                section=section,
                reading_blocks=[],
                frontier=SectionFrontier(),
            )
        }


def _section() -> Section:
    return Section(
        section_id="section-1",
        title="标题",
        level=1,
        parent_section_id=None,
        ordinal=0,
        section_path=["标题"],
        own_span=SourceSpan(0, 12),
        subtree_span=SourceSpan(0, 12),
        preview="正文",
    )


def test_read_request_schemas_forbid_extra_and_limit_batch_size() -> None:
    with pytest.raises(ValidationError):
        ResourceRequest(resource_id="resource-1", extra_field=True)
    with pytest.raises(ValidationError):
        PageContentRequest(
            resource_id="resource-1",
            page_labels=[str(index) for index in range(21)],
        )
    with pytest.raises(ValidationError):
        SectionContentRequest(resource_id="resource-1", section_ids=[])


def test_router_exposes_only_deterministic_read_endpoints() -> None:
    paths = {route.path for route in api_router.routes}
    assert paths == {
        "/resources/document-structure",
        "/resources/page-content",
        "/resources/section-content",
    }


@pytest.mark.asyncio
async def test_structure_response_uses_security_context_permission_scope() -> None:
    reader = _StructureReader()
    SecurityContextHolder.set_group_role_map('{"group-1": 1}')

    response = await document_structure(
        ResourceRequest(resource_id="resource-1"),
        user_id="user-1",
        reader=reader,
    )

    assert response.data.content_revision == "revision-1"
    assert response.data.pages[0].source_span.end_offset == 12
    assert response.data.sections[0].section_id == "section-1"
    assert reader.scope.user_id == "user-1"
    assert reader.scope.group_roles == {"group-1": GroupRoleType.ADMIN}


@pytest.mark.asyncio
async def test_page_response_returns_only_existing_keys() -> None:
    response = await page_content(
        PageContentRequest(
            resource_id="resource-1",
            page_labels=["1", "missing"],
        ),
        user_id="user-1",
        reader=_ContentReader(),
    )

    assert list(response.data) == ["1"]
    assert response.data["1"].text == "正文"


@pytest.mark.asyncio
async def test_empty_section_is_a_successful_existing_section() -> None:
    response = await section_content(
        SectionContentRequest(
            resource_id="resource-1",
            section_ids=["section-1", "missing"],
        ),
        user_id="user-1",
        reader=_ContentReader(),
    )

    assert list(response.data) == ["section-1"]
    assert response.data["section-1"].reading_blocks == []
    assert response.data["section-1"].frontier.children == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("call", "payload", "reader"),
    [
        (
            document_structure,
            ResourceRequest(resource_id="resource-1"),
            _StructureReader(missing=True),
        ),
        (
            page_content,
            PageContentRequest(resource_id="resource-1", page_labels=["1"]),
            _ContentReader(missing=True),
        ),
    ],
)
async def test_missing_or_denied_resource_uses_same_public_error(
    call,
    payload,
    reader,
) -> None:
    with pytest.raises(ServiceException) as error:
        await call(payload, user_id="user-1", reader=reader)

    assert error.value.code == RagErrorCode.RESOURCE_CONTENT_NOT_FOUND.code
    assert error.value.msg == RagErrorCode.RESOURCE_CONTENT_NOT_FOUND.msg
