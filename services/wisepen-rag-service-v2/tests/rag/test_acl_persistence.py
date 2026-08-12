from datetime import UTC, datetime

import pytest
from bson import ObjectId

from rag.core.persistence.mongo.authoritative_acl_reader import (
    AuthoritativeAclError,
    MongoAuthoritativeAclReader,
)
from rag.domain.acl import GroupResourceAcl


class _Collection:
    def __init__(self, record):
        self.record = record
        self.request = None

    async def find_one(self, query):
        self.request = query
        return self.record


@pytest.mark.asyncio
async def test_authoritative_acl_reader_maps_resource_and_group_view_rules() -> None:
    resource_id = str(ObjectId())
    collection = _Collection(
        {
            "_id": ObjectId(resource_id),
            "ownerId": " owner-1 ",
            "updateTime": datetime(2026, 1, 2, tzinfo=UTC),
            "specifiedUsersGrantedActionsMask": {
                "user-1": 2,
                "user-2": 0,
            },
            "computedGroupAcls": {
                "group-1": {
                    "baseMask": 2,
                    "userMasks": {"user-3": 0},
                },
                "group-2": {
                    "baseMask": 0,
                    "userMasks": {"user-4": 2},
                },
            },
        }
    )

    acl = await MongoAuthoritativeAclReader(collection=collection).get_resource_acl(
        resource_id
    )

    assert acl is not None
    assert acl.resource_id == resource_id
    assert acl.owner_id == "owner-1"
    assert acl.readable_users == ["user-1"]
    assert acl.excluded_read_users == ["user-2"]
    assert acl.group_acls == [
        GroupResourceAcl(
            group_id="group-1",
            default_readable=True,
            excluded_read_users=["user-3"],
        ),
        GroupResourceAcl(
            group_id="group-2",
            default_readable=False,
            readable_users=["user-4"],
        ),
    ]


@pytest.mark.asyncio
async def test_authoritative_acl_reader_returns_none_for_missing_resource() -> None:
    collection = _Collection(None)
    resource_id = str(ObjectId())

    assert (
        await MongoAuthoritativeAclReader(collection=collection).get_resource_acl(
            resource_id
        )
        is None
    )


@pytest.mark.asyncio
async def test_authoritative_acl_reader_rejects_invalid_resource_id() -> None:
    with pytest.raises(AuthoritativeAclError):
        await MongoAuthoritativeAclReader(collection=_Collection(None)).get_resource_acl(
            "not-an-object-id"
        )
