"""Mongo adapter：读取上游资源集合中的权威 ACL。"""

from typing import Any

from bson import ObjectId
from pymongo.asynchronous.collection import AsyncCollection

from rag.core.persistence.mongo.mappers.deserializer import (
    AuthoritativeAclError,
    to_authoritative_resource_acl,
)
from rag.domain.acl import ResourceAcl
from rag.domain.repositories.authoritative_acl_reader import AuthoritativeAclReader


class MongoAuthoritativeAclReader(AuthoritativeAclReader):
    """只读上游 ``wisepen_resource_items``，不保存或读取本地 ACL。"""

    __slots__ = ("_collection",)

    def __init__(self, *, collection: AsyncCollection[dict[str, Any]]) -> None:
        self._collection = collection

    async def get_resource_acl(self, resource_id: str) -> ResourceAcl | None:
        if not ObjectId.is_valid(resource_id):
            raise AuthoritativeAclError("resource_id must be a valid ObjectId")

        record = await self._collection.find_one({"_id": ObjectId(resource_id)})
        if record is None:
            return None
        return to_authoritative_resource_acl(record, resource_id)
