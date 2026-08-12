"""Beanie adapter：维护本地资源 ACL，不读取上游权限集合。"""

from collections.abc import Mapping, Sequence

from beanie.operators import In
from pymongo.errors import DuplicateKeyError

from rag.core.persistence.mongo.mappers.deserializer import to_resource_acl
from rag.core.persistence.mongo.mappers.serializer import resource_acl_document
from rag.domain.acl import ResourceAcl
from rag.domain.entities import ResourceAclEntity
from rag.domain.repositories.resource_acl_store import ResourceAclStore


class MongoResourceAclStore(ResourceAclStore):
    """按资源 ID 查询并按 ACL revision 单调写入本地 ACL。"""

    async def get_resource_acls(
        self,
        resource_ids: Sequence[str],
    ) -> Mapping[str, ResourceAcl]:
        unique_resource_ids = list(dict.fromkeys(resource_ids))
        if not unique_resource_ids:
            return {}
        entities = await ResourceAclEntity.find(
            In(ResourceAclEntity.resource_id, unique_resource_ids)
        ).to_list()
        return {entity.resource_id: to_resource_acl(entity) for entity in entities}

    async def save_if_newer(self, resource_acl: ResourceAcl) -> bool:
        collection = ResourceAclEntity.get_pymongo_collection()
        document = resource_acl_document(resource_acl)
        try:
            result = await collection.update_one(
                {
                    "resource_id": resource_acl.resource_id,
                    "$or": [
                        {"acl_revision": {"$lt": resource_acl.acl_revision}},
                        {"acl_revision": {"$exists": False}},
                    ],
                },
                {"$set": document},
                upsert=False,
            )
            if result.matched_count:
                return True

            existing = await ResourceAclEntity.find_one(
                ResourceAclEntity.resource_id == resource_acl.resource_id
            )
            if existing is not None:
                return False

            await collection.insert_one(document)
            return True
        except DuplicateKeyError:
            return False

    async def delete_resources(self, resource_ids: Sequence[str]) -> None:
        unique_resource_ids = list(dict.fromkeys(resource_ids))
        if unique_resource_ids:
            await ResourceAclEntity.find(
                In(ResourceAclEntity.resource_id, unique_resource_ids)
            ).delete()
