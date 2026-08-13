"""按页或 Section 获取已发布正文。"""

from collections.abc import Sequence

from rag.application.rag.acl import PermissionAuthorizer
from rag.domain.models.acl import PermissionScope
from rag.domain.models.content import ContentWindow, SectionContent
from rag.domain.repositories.mongo.readers.applied_content import AppliedContentReader


class ContentNotFoundError(RuntimeError):
    """资源没有可读取的 applied revision。"""


class ContentAccessRevokedError(RuntimeError):
    """读取期间资源失去可读权限。"""


class DocumentContentReader:
    """读取 applied revision 的 page 和 Section 正文。"""

    __slots__ = ("_authorizer", "_reader")

    def __init__(
        self,
        *,
        reader: AppliedContentReader,
        authorizer: PermissionAuthorizer,
    ) -> None:
        self._reader = reader
        self._authorizer = authorizer

    async def get_pages(
        self,
        *,
        resource_id: str,
        page_labels: Sequence[str],
        permission_scope: PermissionScope,
    ) -> dict[str, ContentWindow]:
        if not await self._authorizer.authorize_resource(
            resource_id=resource_id,
            scope=permission_scope,
        ):
            raise ContentNotFoundError(resource_id)
        pages = await self._reader.get_applied_pages(resource_id, page_labels)
        if pages is None:
            raise ContentNotFoundError(resource_id)
        if not await self._authorizer.authorize_resource(
            resource_id=resource_id,
            scope=permission_scope,
        ):
            raise ContentAccessRevokedError(resource_id)
        return pages

    async def get_sections(
        self,
        *,
        resource_id: str,
        section_ids: Sequence[str],
        permission_scope: PermissionScope,
    ) -> dict[str, SectionContent]:
        if not await self._authorizer.authorize_resource(
            resource_id=resource_id,
            scope=permission_scope,
        ):
            raise ContentNotFoundError(resource_id)
        sections = await self._reader.get_applied_sections(resource_id, section_ids)
        if sections is None:
            raise ContentNotFoundError(resource_id)
        if not await self._authorizer.authorize_resource(
            resource_id=resource_id,
            scope=permission_scope,
        ):
            raise ContentAccessRevokedError(resource_id)
        return sections
