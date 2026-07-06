from __future__ import annotations

from datetime import datetime, timezone

from chat.application.rag.acl import (
    RagAclProjectionProjector,
    RagComputedGroupAclProjection,
    RagResourceAclProjection,
)
from chat.domain.entities.rag_acl import (
    RagAclProjectionDocument,
    RagComputedGroupAclProjectionDocument,
)

_RESOURCE_ITEMS_COLLECTION = "wisepen_resource_items"


class MongoRagAclProjectionRepository:
    __slots__ = ("_projector",)

    def __init__(self, *, projector: RagAclProjectionProjector) -> None:
        self._projector = projector

    async def get_projection(self, resource_id: str) -> RagResourceAclProjection | None:
        document = await RagAclProjectionDocument.find_one(
            RagAclProjectionDocument.resource_id == resource_id
        )
        if document is None:
            return None
        return _to_projection(document)

    async def load_resource_projection(self, resource_id: str) -> RagResourceAclProjection | None:
        raw = await RagAclProjectionDocument.get_motor_collection().database[
            _RESOURCE_ITEMS_COLLECTION
        ].find_one({"_id": resource_id})
        if raw is None:
            return None
        return self._projector.from_resource_item(raw)

    async def upsert_projection(self, projection: RagResourceAclProjection) -> None:
        now = datetime.now(timezone.utc)
        document = await RagAclProjectionDocument.find_one(
            RagAclProjectionDocument.resource_id == projection.resource_id
        )
        if document is None:
            document = RagAclProjectionDocument(
                resource_id=projection.resource_id,
                owner_id=projection.owner_id,
                specified_discover_users=list(projection.specified_discover_users),
                computed_group_acls=_to_group_documents(projection),
                created_at=now,
                updated_at=now,
            )
            await document.insert()
            return

        document.owner_id = projection.owner_id
        document.specified_discover_users = list(projection.specified_discover_users)
        document.computed_group_acls = _to_group_documents(projection)
        document.updated_at = now
        await document.save()


def _to_projection(document: RagAclProjectionDocument) -> RagResourceAclProjection:
    return RagResourceAclProjection(
        resource_id=document.resource_id,
        owner_id=document.owner_id,
        specified_discover_users=tuple(document.specified_discover_users),
        computed_group_acls=tuple(
            RagComputedGroupAclProjection(
                group_id=item.group_id,
                is_discover=item.is_discover,
                specified_users=tuple(item.specified_users),
            )
            for item in document.computed_group_acls
        ),
    )


def _to_group_documents(
        projection: RagResourceAclProjection,
) -> list[RagComputedGroupAclProjectionDocument]:
    return [
        RagComputedGroupAclProjectionDocument(
            group_id=item.group_id,
            is_discover=item.is_discover,
            specified_users=list(item.specified_users),
        )
        for item in projection.computed_group_acls
    ]
