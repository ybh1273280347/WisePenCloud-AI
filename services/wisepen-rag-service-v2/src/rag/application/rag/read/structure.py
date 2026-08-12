"""获取已发布文档结构，不读取 page 或 Section 正文。"""

from rag.application.rag.acl import PermissionAuthorizer
from rag.domain.acl import PermissionScope
from rag.domain.read_content import DocumentStructureResult
from rag.domain.repositories.mongo.readers.applied_structure import AppliedStructureReader

from .content import ContentNotFoundError


class DocumentStructureReader:
    """读取 applied revision 的结构事实，不读取正文。"""

    __slots__ = ("_authorizer", "_reader")

    def __init__(
        self,
        *,
        reader: AppliedStructureReader,
        authorizer: PermissionAuthorizer,
    ) -> None:
        self._reader = reader
        self._authorizer = authorizer

    async def get(
        self,
        *,
        resource_id: str,
        permission_scope: PermissionScope,
    ) -> DocumentStructureResult:
        if not await self._authorizer.authorize_resource(
            resource_id=resource_id,
            scope=permission_scope,
        ):
            raise ContentNotFoundError(resource_id)
        structure = await self._reader.get_applied_document_structure(resource_id)
        if structure is None:
            raise ContentNotFoundError(resource_id)
        return structure
