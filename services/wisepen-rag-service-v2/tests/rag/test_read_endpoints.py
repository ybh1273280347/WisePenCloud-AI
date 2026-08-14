import pytest
from common.core.domain import GroupRoleType
from common.security import SecurityContextHolder
from pydantic import TypeAdapter, ValidationError

from rag.api.endpoints.read import (
    get_document_outline,
    get_page_content,
)
from rag.api.router import api_router
from rag.api.schemas import PageContentRequest, ResourceRequest, SectionContentRequest
from rag.application.rag.read.content import (
    DocumentContentReader,
    PageContentView,
    SectionAnchorView,
    SectionContentView,
)
from rag.application.rag.read.outline import (
    DocumentOutlineNode,
    DocumentOutlineResult,
    _to_outline,
)
from rag.domain.models.acl import PermissionScope
from rag.domain.models.content import (
    ContentRevision,
    ContentWindow,
    SectionContent,
    SectionFrontier,
)
from rag.domain.models.structure import PageRange, Section, StructureMode
from rag.utils.chunkers import SourceSpan


class _AllowAuthorizer:
    async def authorize_resource(self, *, resource_id, scope) -> bool:
        return True


class _PublishedResourceReader:
    async def get_pages(self, resource_id, page_labels):
        return {
            "1": ContentWindow(
                text="<!-- page 1 -->\n正文",
                source_span=SourceSpan(0, 22),
                page_labels=["1"],
                sections=[_section()],
                anchor_labels=["Table 1"],
            )
        }

    async def get_sections(self, resource_id, section_ids):
        return {
            "section-1": SectionContent(
                section=_section(),
                text="正文",
                page_labels=["1"],
                anchor_labels=["Table 1"],
                frontier=SectionFrontier(children=[_child_section()]),
            )
        }


class _ContentReader:
    async def get_pages(self, **kwargs):
        return {
            "1": PageContentView(
                text="正文",
                page_range="1",
                sections=[
                    SectionAnchorView(
                        section_id="section-1",
                        title="标题",
                        section_path="标题",
                    )
                ],
            )
        }

    async def get_sections(self, **kwargs):
        return {
            "section-1": SectionContentView(
                title="标题",
                section_path="标题",
                text="正文",
                page_range="1",
            )
        }


class _OutlineReader:
    def __init__(self) -> None:
        self.scope = None

    async def get_document_outline(self, *, resource_id, permission_scope):
        self.scope = permission_scope
        return DocumentOutlineResult(
            revision=ContentRevision(
                resource_id=resource_id,
                content_revision="revision-1",
                document_version=3,
                content_hash="hash",
                index_schema_version="rag-v2-content:v2",
                structure_mode=StructureMode.SECTIONED,
                total_length=12,
            ),
            outline=[
                DocumentOutlineNode(
                    section_id="section-1",
                    title="标题",
                    section_path="标题",
                    page_range="1",
                )
            ],
        )


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
        content_spans=[SourceSpan(4, 12)],
        preview="正文",
    )


def _child_section() -> Section:
    return Section(
        section_id="section-2",
        title="子标题",
        level=2,
        parent_section_id="section-1",
        ordinal=0,
        section_path=["标题", "子标题"],
        own_span=SourceSpan(6, 12),
        subtree_span=SourceSpan(6, 12),
        content_spans=[SourceSpan(9, 12)],
        preview="子正文",
    )


def test_read_request_schemas_and_routes() -> None:
    with pytest.raises(ValidationError):
        ResourceRequest(resource_id="resource-1", extra_field=True)
    with pytest.raises(ValidationError):
        PageContentRequest(
            resource_id="resource-1",
            page_labels=[str(index) for index in range(21)],
        )
    with pytest.raises(ValidationError):
        SectionContentRequest(resource_id="resource-1", section_ids=[])

    paths = {route.path for route in api_router.routes}
    assert "/getDocumentOutline" in paths
    assert "/getPageContent" in paths
    assert "/getSectionContent" in paths
    assert "/expandDiscoveredSections" not in paths


@pytest.mark.asyncio
async def test_outline_keeps_title_and_path_and_removes_level() -> None:
    reader = _OutlineReader()
    SecurityContextHolder.set_group_role_map('{"group-1": 1}')

    response = await get_document_outline(
        ResourceRequest(resource_id="resource-1"),
        user_id="user-1",
        reader=reader,
    )

    node = response.data.outline[0]
    assert node.title == "标题"
    assert node.section_path == "标题"
    assert node.page_range == "1"
    assert not hasattr(node, "level")
    assert reader.scope.group_roles == {"group-1": GroupRoleType.ADMIN}


@pytest.mark.asyncio
async def test_page_key_is_not_repeated_and_has_no_preview() -> None:
    response = await get_page_content(
        PageContentRequest(resource_id="resource-1", page_labels=["1"]),
        user_id="user-1",
        reader=_ContentReader(),
    )

    page = response.data["1"]
    payload = TypeAdapter(PageContentView).dump_python(
        page,
        mode="json",
        exclude_none=True,
    )
    assert page.sections[0].title == "标题"
    assert "page_label" not in payload
    assert "preview" not in payload["sections"][0]
    assert "level" not in payload["sections"][0]


@pytest.mark.asyncio
async def test_section_read_returns_authoritative_text_without_blocks() -> None:
    reader = DocumentContentReader(
        reader=_PublishedResourceReader(),
        authorizer=_AllowAuthorizer(),
    )
    sections = await reader.get_sections(
        resource_id="resource-1",
        section_ids=["section-1"],
        permission_scope=PermissionScope(user_id="user-1"),
    )

    view = sections["section-1"]
    payload = TypeAdapter(SectionContentView).dump_python(
        view,
        mode="json",
        exclude_none=True,
    )
    assert view.title == "标题"
    assert view.text == "正文"
    assert view.page_range == "1"
    assert view.navigation.children[0].title == "子标题"
    assert view.navigation.children[0].preview == "子正文"
    assert "section_id" not in payload
    assert "section" not in payload
    assert "reading_blocks" not in payload
    assert "level" not in payload["navigation"]["children"][0]


@pytest.mark.asyncio
async def test_flat_text_read_keeps_synthetic_section_context() -> None:
    reader = DocumentContentReader(
        reader=_FlatPublishedResourceReader(),
        authorizer=_AllowAuthorizer(),
    )
    pages = await reader.get_pages(
        resource_id="flat-resource",
        page_labels=["1"],
        permission_scope=PermissionScope(user_id="user-1"),
    )
    sections = await reader.get_sections(
        resource_id="flat-resource",
        section_ids=["flat-section"],
        permission_scope=PermissionScope(user_id="user-1"),
    )

    page_payload = TypeAdapter(PageContentView).dump_python(
        pages["1"], mode="json", exclude_none=True
    )
    section_payload = TypeAdapter(SectionContentView).dump_python(
        sections["flat-section"], mode="json", exclude_none=True
    )
    assert page_payload["page_range"] == "1"
    assert page_payload["sections"] == [
        {
            "section_id": "flat-section",
            "title": "全文片段 1",
            "section_path": "全文片段 1",
        }
    ]
    assert section_payload == {
        "title": "全文片段 1",
        "section_path": "全文片段 1",
        "text": "平铺正文",
        "page_range": "1",
        "anchor_labels": [],
        "navigation": {"children": []},
    }


def test_outline_uses_human_page_range() -> None:
    outline = _to_outline(
        [_section(), _child_section()],
        [
            PageRange(0, "1", SourceSpan(0, 6)),
            PageRange(1, "3", SourceSpan(6, 12)),
        ],
    )

    assert outline[0].page_range == "1 - 3"
    assert outline[0].section_path == "标题"
    assert outline[0].children[0].page_range == "3"
    assert outline[0].children[0].section_path == "标题 > 子标题"

    flat_outline = _to_outline([_flat_section()], [])
    assert flat_outline[0].page_range is None
    assert flat_outline[0].title == "全文片段 1"
    assert flat_outline[0].section_path == "全文片段 1"
    assert flat_outline[0].children == []


class _FlatPublishedResourceReader:
    async def get_pages(self, resource_id, page_labels):
        return {
            "1": ContentWindow(
                text="平铺正文",
                source_span=SourceSpan(0, 4),
                page_labels=["1"],
                sections=[_flat_section()],
            )
        }

    async def get_sections(self, resource_id, section_ids):
        return {
            "flat-section": SectionContent(
                section=_flat_section(),
                text="平铺正文",
                page_labels=["1"],
            )
        }


def _flat_section() -> Section:
    return Section(
        section_id="flat-section",
        title="全文片段 1",
        level=1,
        parent_section_id=None,
        ordinal=0,
        section_path=["全文片段 1"],
        own_span=SourceSpan(0, 4),
        subtree_span=SourceSpan(0, 4),
        content_spans=[SourceSpan(0, 4)],
    )
