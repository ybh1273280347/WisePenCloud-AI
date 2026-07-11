from __future__ import annotations

from datetime import datetime, timezone

from bson import ObjectId

from chat.application.rag.acl import (
    RagAclProjectionProjector,
    RagComputedGroupAclProjection,
    RagResourceAclProjection,
)
from chat.domain.entities.rag_acl import (
    RagAclProjectionDocument,
    RagComputedGroupAclProjectionDocument,
)

_RESOURCE_ITEMS_COLLECTION = "wisepen_resource_items"  # resource-service 原始资源集合，用于回源查询


class MongoRagAclProjectionRepository:
    """ACL 投影的 MongoDB 持久化实现。

    - get_projection: 从投影集合查询已缓存的权限投影
    - load_resource_projection: 从 resource-service 原始集合回源查询并构建投影
    - upsert_projection: 写入或更新投影文档
    """

    __slots__ = ("_projector", "_resource_database_name")

    def __init__(
            self,
            *,
            projector: RagAclProjectionProjector,
            resource_database_name: str,
    ) -> None:
        self._projector = projector
        self._resource_database_name = resource_database_name

    async def get_projection(self, resource_id: str) -> RagResourceAclProjection | None:
        document = await RagAclProjectionDocument.find_one(
            RagAclProjectionDocument.resource_id == resource_id
        )
        if document is None:
            return None
        return RagResourceAclProjection(
            resource_id=document.resource_id,
            owner_id=document.owner_id,
            readable_users=tuple(document.readable_users),
            computed_group_acls=tuple(
                RagComputedGroupAclProjection(
                    group_id=item.group_id,
                    is_readable=item.is_readable,
                    readable_users=tuple(item.readable_users),
                    excluded_read_users=tuple(item.excluded_read_users),
                )
                for item in document.computed_group_acls
            ),
        )

    async def load_resource_projection(self, resource_id: str) -> RagResourceAclProjection | None:
        projection_collection = RagAclProjectionDocument.get_pymongo_collection()
        resource_collection = projection_collection.database.client[
            self._resource_database_name
        ][_RESOURCE_ITEMS_COLLECTION]
        raw = await resource_collection.find_one(_resource_item_query(resource_id))
        if raw is None:
            return None
        return self._projector.from_resource_item({**raw, "_id": str(raw["_id"])})

    async def upsert_projection(self, projection: RagResourceAclProjection) -> None:
        now = datetime.now(timezone.utc)
        document = await RagAclProjectionDocument.find_one(
            RagAclProjectionDocument.resource_id == projection.resource_id
        )
        if document is None:
            document = RagAclProjectionDocument(
                resource_id=projection.resource_id,
                owner_id=projection.owner_id,
                readable_users=list(projection.readable_users),
                computed_group_acls=_to_group_documents(projection),
                created_at=now,
                updated_at=now,
            )
            await document.insert()
            return

        document.owner_id = projection.owner_id
        document.readable_users = list(projection.readable_users)
        document.computed_group_acls = _to_group_documents(projection)
        document.updated_at = now
        await document.save()


def _to_group_documents(
        projection: RagResourceAclProjection,
) -> list[RagComputedGroupAclProjectionDocument]:
    return [
        RagComputedGroupAclProjectionDocument(
            group_id=item.group_id,
            is_readable=item.is_readable,
            readable_users=list(item.readable_users),
            excluded_read_users=list(item.excluded_read_users),
        )
        for item in projection.computed_group_acls
    ]


def _resource_item_query(resource_id: str) -> dict[str, object]:
    if ObjectId.is_valid(resource_id):
        return {"_id": ObjectId(resource_id)}
    return {"_id": resource_id}
