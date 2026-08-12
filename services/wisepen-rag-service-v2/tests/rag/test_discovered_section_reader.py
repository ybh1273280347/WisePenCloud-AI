import pytest

from rag.application.rag.acl import PermissionAuthorizer
from rag.application.rag.read import (
    DiscoveredSectionReader,
    SectionAccessRevokedError,
    SectionNotDiscoveredError,
    SectionRevisionChangedError,
)
from rag.domain.acl import PermissionScope, ResourceAcl
from rag.domain.content_revision import ContentRevision
from rag.domain.document_structure import Section, StructureMode
from rag.domain.navigation import (
    KnownSection,
    NavigationState,
    NavigationStateNotFoundError,
)
from rag.domain.read_content import SectionContent, SectionFrontier
from rag.utils.chunkers import SourceSpan


class _StateStore:
    def __init__(self, state) -> None:
        self.state = state
        self.added = []

    async def get(self, state_id):
        return self.state

    async def add_known_sections(self, **kwargs):
        self.added.append(kwargs)


class _ContentReader:
    def __init__(self, sections) -> None:
        self.sections = sections

    async def get_applied_sections(self, resource_id, section_ids):
        return {
            section_id: self.sections[section_id]
            for section_id in section_ids
            if section_id in self.sections
        }


class _RevisionReader:
    def __init__(self, revision) -> None:
        self.revision = revision

    async def get_applied_revision(self, resource_id):
        return self.revision


class _AclReader:
    def __init__(self, readable=True) -> None:
        self.readable = readable

    async def get_resource_acls(self, resource_ids):
        if not self.readable:
            return {}
        return {
            resource_id: ResourceAcl(
                resource_id=resource_id,
                acl_revision=1,
                owner_id="user-1",
            )
            for resource_id in resource_ids
        }


@pytest.mark.asyncio
async def test_reader_reads_known_section_and_adds_frontier() -> None:
    revision = _revision()
    section = _section("section-1")
    child = _section("child", parent_section_id="section-1")
    state_store = _StateStore(_state())
    reader = _reader(
        revision=revision,
        state_store=state_store,
        sections={
            "section-1": SectionContent(
                section=section,
                frontier=SectionFrontier(children=[child]),
            )
        },
    )

    result = await reader.get(
        state_id="nav-1",
        session_id="session-1",
        permission_scope=PermissionScope(user_id="user-1"),
        section_ids=["section-1"],
    )

    assert list(result) == ["section-1"]
    assert set(state_store.added[0]["sections"]) == {"section-1", "child"}


@pytest.mark.asyncio
async def test_reader_rejects_unknown_section_and_state_owner() -> None:
    reader = _reader(revision=_revision(), state_store=_StateStore(_state()))

    with pytest.raises(SectionNotDiscoveredError):
        await reader.get(
            state_id="nav-1",
            session_id="session-1",
            permission_scope=PermissionScope(user_id="user-1"),
            section_ids=["unknown"],
        )
    with pytest.raises(NavigationStateNotFoundError):
        await reader.get(
            state_id="nav-1",
            session_id="other-session",
            permission_scope=PermissionScope(user_id="user-1"),
            section_ids=["section-1"],
        )
    with pytest.raises(NavigationStateNotFoundError):
        await reader.get(
            state_id="nav-1",
            session_id="session-1",
            permission_scope=PermissionScope(user_id="other-user"),
            section_ids=["section-1"],
        )


@pytest.mark.asyncio
async def test_reader_rejects_revision_change_and_acl_revocation() -> None:
    changed = _revision()
    changed.content_revision = "revision-2"
    with pytest.raises(SectionRevisionChangedError):
        await _reader(
            revision=changed,
            state_store=_StateStore(_state()),
        ).get(
            state_id="nav-1",
            session_id="session-1",
            permission_scope=PermissionScope(user_id="user-1"),
            section_ids=["section-1"],
        )

    with pytest.raises(SectionAccessRevokedError):
        await _reader(
            revision=_revision(),
            state_store=_StateStore(_state()),
            readable=False,
        ).get(
            state_id="nav-1",
            session_id="session-1",
            permission_scope=PermissionScope(user_id="user-1"),
            section_ids=["section-1"],
        )


def _reader(
    *,
    revision,
    state_store,
    sections=None,
    readable=True,
) -> DiscoveredSectionReader:
    return DiscoveredSectionReader(
        content_reader=_ContentReader(sections or {}),
        revision_reader=_RevisionReader(revision),
        authorizer=PermissionAuthorizer(reader=_AclReader(readable)),
        state_store=state_store,
    )


def _state() -> NavigationState:
    return NavigationState(
        state_id="nav-1",
        user_id="user-1",
        session_id="session-1",
        root_query="问题",
        known_sections={
            "section-1": KnownSection(
                resource_id="resource-1",
                content_revision="revision-1",
            )
        },
    )


def _revision() -> ContentRevision:
    return ContentRevision(
        resource_id="resource-1",
        content_revision="revision-1",
        document_version=1,
        content_hash="hash",
        index_schema_version="v1",
        structure_mode=StructureMode.SECTIONED,
        total_length=10,
    )


def _section(section_id, *, parent_section_id=None) -> Section:
    return Section(
        section_id=section_id,
        title=section_id,
        level=1,
        parent_section_id=parent_section_id,
        ordinal=0,
        section_path=[section_id],
        own_span=SourceSpan(0, 10),
        subtree_span=SourceSpan(0, 10),
    )
