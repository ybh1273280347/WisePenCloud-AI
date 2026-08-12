"""Beanie adapter：维护本地资源 ACL，不读取上游权限集合。"""

from collections.abc import Mapping, Sequence

from beanie.operators import In
from pymongo.errors import DuplicateKeyError

from rag.domain.entities import ResourceAclEntity
from rag.domain.models.acl import GroupResourceAcl, ResourceAcl
from rag.domain.repositories.mongo.resource_acl_store import ResourceAclStore


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
        return {entity.resource_id: _to_domain(entity) for entity in entities}

    async def save_if_newer(self, resource_acl: ResourceAcl) -> bool:
        collection = ResourceAclEntity.get_pymongo_collection()
        document = _to_document(resource_acl)
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


def _to_domain(entity: ResourceAclEntity) -> ResourceAcl:
    return ResourceAcl(
        resource_id=entity.resource_id,
        acl_revision=entity.acl_revision,
        owner_id=entity.owner_id,
        readable_users=list(entity.readable_users),
        excluded_read_users=list(entity.excluded_read_users),
        group_acls=[
            GroupResourceAcl(
                group_id=group_acl.group_id,
                default_readable=group_acl.is_readable,
                readable_users=list(group_acl.readable_users),
                excluded_read_users=list(group_acl.excluded_read_users),
            )
            for group_acl in entity.group_acls
        ],
    )


def _to_document(resource_acl: ResourceAcl) -> dict[str, object]:
    return {
        "resource_id": resource_acl.resource_id,
        "acl_revision": resource_acl.acl_revision,
        "owner_id": resource_acl.owner_id,
        "readable_users": list(resource_acl.readable_users),
        "excluded_read_users": list(resource_acl.excluded_read_users),
        "group_acls": [
            {
                "group_id": group_acl.group_id,
                "is_readable": group_acl.default_readable,
                "readable_users": list(group_acl.readable_users),
                "excluded_read_users": list(group_acl.excluded_read_users),
            }
            for group_acl in resource_acl.group_acls
        ],
    }
