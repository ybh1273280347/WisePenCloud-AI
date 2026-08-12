"""沿 navigation state 扩展标题树，并返回本次展开的 Section 内容。"""

from collections.abc import Sequence
from dataclasses import dataclass, field

from rag.application.rag.acl import PermissionAuthorizer
from rag.domain.models.acl import PermissionScope
from rag.domain.models.navigation import (
    KnownSection,
    NavigationStateNotFoundError,
)
from rag.domain.models.content import SectionView
from rag.domain.repositories.mongo.readers.applied_content import AppliedContentReader
from rag.domain.repositories.mongo.readers.applied_revision import AppliedRevisionReader
from rag.domain.repositories.redis.navigation_state_store import NavigationStateStore


class SectionNotDiscoveredError(RuntimeError):
    """请求的 Section 尚未被当前 navigation state 发现。"""


class SectionAccessRevokedError(RuntimeError):
    """Section 所属资源在读取期间已不可访问。"""


class SectionRevisionChangedError(RuntimeError):
    """Section 所属资源的 applied revision 已发生变化。"""


class SectionRecordMissingError(RuntimeError):
    """state 中的已知 Section 在对应 applied revision 中缺失。"""


@dataclass(slots=True)
class SectionExpandResult:
    """标题树展开结果，sections 保留请求顺序供 Agent 连续阅读。"""

    state_id: str
    sections: list[SectionView] = field(default_factory=list)


class SectionTreeExpander:
    """读取已发现 Section 内容后，将相邻标题节点写回探索状态。"""

    def __init__(
        self,
        *,
        content_reader: AppliedContentReader,
        revision_reader: AppliedRevisionReader,
        authorizer: PermissionAuthorizer,
        state_store: NavigationStateStore,
    ) -> None:
        self._content_reader = content_reader
        self._revision_reader = revision_reader
        self._authorizer = authorizer
        self._state_store = state_store

    async def expand(
        self,
        *,
        state_id: str,
        session_id: str,
        permission_scope: PermissionScope,
        section_ids: Sequence[str],
    ) -> SectionExpandResult:
        state = await self._state_store.get(state_id)
        if (
            state is None
            or state.user_id != permission_scope.user_id
            or state.session_id != session_id
        ):
            raise NavigationStateNotFoundError(state_id)

        requested_ids = list(dict.fromkeys(section_ids))
        unknown_ids = [
            section_id
            for section_id in requested_ids
            if section_id not in state.known_sections
        ]
        if unknown_ids:
            raise SectionNotDiscoveredError(unknown_ids[0])
        if not requested_ids:
            return SectionExpandResult(state_id=state.state_id)

        ids_by_resource: dict[str, list[str]] = {}
        expected_revisions: dict[str, str] = {}
        for section_id in requested_ids:
            known = state.known_sections[section_id]
            expected = expected_revisions.setdefault(
                known.resource_id,
                known.content_revision,
            )
            if expected != known.content_revision:
                raise SectionRevisionChangedError(known.resource_id)
            ids_by_resource.setdefault(known.resource_id, []).append(section_id)

        await self._verify_resources(
            ids_by_resource,
            expected_revisions,
            permission_scope,
        )
        contents_by_id = {}
        for resource_id, resource_section_ids in ids_by_resource.items():
            sections = await self._content_reader.get_applied_sections(
                resource_id,
                resource_section_ids,
            )
            if sections is None:
                raise SectionRevisionChangedError(resource_id)
            missing_ids = [
                section_id
                for section_id in resource_section_ids
                if section_id not in sections
            ]
            if missing_ids:
                raise SectionRecordMissingError(missing_ids[0])
            contents_by_id.update(sections)

        # 权限或 revision 可能在正文查询期间变化，返回前必须再次 fail closed。
        await self._verify_resources(
            ids_by_resource,
            expected_revisions,
            permission_scope,
        )
        discovered: dict[str, KnownSection] = {}
        section_views: list[SectionView] = []
        for section_id in requested_ids:
            content = contents_by_id[section_id]
            known = state.known_sections[content.section.section_id]
            for section in (
                content.section,
                content.frontier.parent,
                content.frontier.previous,
                content.frontier.next,
                *content.frontier.children,
            ):
                if section is not None:
                    discovered[section.section_id] = KnownSection(
                        resource_id=known.resource_id,
                        content_revision=known.content_revision,
                    )
            section_views.append(
                SectionView(
                    resource_id=known.resource_id,
                    content_revision=known.content_revision,
                    section=content.section,
                    reading_blocks=content.reading_blocks,
                    frontier=content.frontier,
                )
            )
        await self._state_store.add_known_sections(
            state_id=state.state_id,
            sections=discovered,
        )
        return SectionExpandResult(state_id=state.state_id, sections=section_views)

    async def _verify_resources(
        self,
        ids_by_resource: dict[str, list[str]],
        expected_revisions: dict[str, str],
        permission_scope: PermissionScope,
    ) -> None:
        resource_ids = list(ids_by_resource)
        readable = set(
            await self._authorizer.readable_resource_ids(
                resource_ids,
                scope=permission_scope,
            )
        )
        denied = next(
            (resource_id for resource_id in resource_ids if resource_id not in readable),
            None,
        )
        if denied is not None:
            raise SectionAccessRevokedError(denied)

        for resource_id in resource_ids:
            revision = await self._revision_reader.get_applied_revision(resource_id)
            if (
                revision is None
                or revision.content_revision != expected_revisions[resource_id]
            ):
                raise SectionRevisionChangedError(resource_id)
