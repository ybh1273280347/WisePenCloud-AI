from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from chat.application.rag.acl import RagResourceAclProjection
from .models import RagGraphEnhancementRequest, RagGraphEnhancementResult

if TYPE_CHECKING:
    pass


class RagGraphRepository(Protocol):
    async def delete_document_projection(
            self,
            *,
            resource_id: str,
            document_version: str,
    ) -> None:
        ...

    async def update_acl_projection(self, projection: RagResourceAclProjection) -> None:
        ...

    async def expand_for_warnings(
            self,
            request: RagGraphEnhancementRequest,
    ) -> RagGraphEnhancementResult:
        ...
