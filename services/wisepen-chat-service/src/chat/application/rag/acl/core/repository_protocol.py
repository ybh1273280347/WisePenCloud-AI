from __future__ import annotations

from typing import Protocol

from .models import RagResourceAclProjection


class RagAclProjectionRepository(Protocol):
    async def upsert_projection(self, projection: RagResourceAclProjection) -> None:
        ...

    async def get_projection(self, resource_id: str) -> RagResourceAclProjection | None:
        ...

    async def load_resource_projection(self, resource_id: str) -> RagResourceAclProjection | None:
        ...
