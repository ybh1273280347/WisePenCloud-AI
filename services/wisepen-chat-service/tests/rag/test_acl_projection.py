from __future__ import annotations

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from chat.application.rag.acl import (  # noqa: E402
    RagAclProjectionError,
    RagAclProjectionProjector,
    RagAclProjectionUpdater,
    RagResourceAclProjection,
)
from chat.application.rag.kafka_consumers.acl_recalculate_consumer import (  # noqa: E402
    RagAclRecalculateConsumer,
    parse_acl_recalculate_message,
)
from chat.core.persistence.mongo.rag_acl_projection_repository import (  # noqa: E402
    MongoRagAclProjectionRepository,
)
from chat.domain.entities.rag_acl import RagAclProjectionDocument  # noqa: E402


def test_parse_acl_recalculate_message_uses_real_resource_topic_fields() -> None:
    message = parse_acl_recalculate_message(
        {
            "resourceId": "res-1",
            "triggerSource": "TAG_CHANGED",
        }
    )

    assert message.resource_id == "res-1"
    assert message.trigger_source == "TAG_CHANGED"


def test_parse_acl_recalculate_message_rejects_non_string_resource_id() -> None:
    with pytest.raises(RagAclProjectionError):
        parse_acl_recalculate_message(
            {
                "resourceId": 123,
                "triggerSource": "TAG_CHANGED",
            }
        )


def test_acl_projection_from_resource_item_uses_view_permission_not_discover() -> None:
    projection = RagAclProjectionProjector().from_resource_item(
        {
            "_id": "res-1",
            "ownerId": "owner-1",
            "specifiedUsersGrantedActionsMask": {
                "discover-only": 1,
                "view-user": 2,
            },
            "computedGroupAcls": {
                "101": {
                    "baseMask": 3,
                    "userMasks": {
                        "blocked-user": 1,
                    },
                },
                "102": {
                    "baseMask": 1,
                    "userMasks": {
                        "allowed-user": 2,
                    },
                },
            },
        }
    )

    assert projection.readable_users == ("view-user",)
    assert projection.computed_group_acls[0].is_readable
    assert projection.computed_group_acls[0].excluded_read_users == ("blocked-user",)
    assert not projection.computed_group_acls[1].is_readable
    assert projection.computed_group_acls[1].readable_users == ("allowed-user",)


def test_acl_projection_from_resource_item_ignores_invalid_acl_ids_and_masks() -> None:
    projection = RagAclProjectionProjector().from_resource_item(
        {
            "_id": "res-1",
            "ownerId": "owner-1",
            "specifiedUsersGrantedActionsMask": {
                "view-user": 2,
                123: 2,
                "string-mask": "2",
            },
            "computedGroupAcls": {
                "101": {
                    "baseMask": "2",
                    "userMasks": {
                        "allowed-user": 2,
                        123: 2,
                        "string-mask": "2",
                    },
                },
                102: {
                    "baseMask": 2,
                    "userMasks": {},
                },
            },
        }
    )

    assert projection.readable_users == ("view-user",)
    assert len(projection.computed_group_acls) == 1
    assert projection.computed_group_acls[0].group_id == "101"
    assert projection.computed_group_acls[0].readable_users == ("allowed-user",)


@pytest.mark.anyio
async def test_acl_projection_service_always_loads_resource_projection() -> None:
    repository = _RecordingAclProjectionRepository()
    updater = _RecordingAclProjectionUpdater()
    source_projection = RagResourceAclProjection(
        resource_id="res-1",
        owner_id="owner-from-resource-item",
        computed_group_acls=(),
    )
    repository.source_projection = source_projection
    service = RagAclRecalculateConsumer(
        repository=repository,
        updater=updater,
    )

    await service.handle(
        {
            "resourceId": "res-1",
            "triggerSource": "RESOURCE_ACTION_PERMISSION_CHANGED",
            "ownerId": "stale-owner-from-message",
            "computedGroupAcls": [],
        }
    )

    assert repository.load_calls == ["res-1"]
    assert repository.saved is not None
    assert repository.saved.resource_id == "res-1"
    assert repository.saved.owner_id == "owner-from-resource-item"
    assert updater.updated == [repository.saved]


@pytest.mark.anyio
async def test_acl_projection_service_fetches_projection_for_recalc_event() -> None:
    repository = _RecordingAclProjectionRepository()
    source_projection = RagResourceAclProjection(
        resource_id="res-2",
        owner_id="owner-2",
        computed_group_acls=(),
    )
    repository.source_projection = source_projection
    service = RagAclRecalculateConsumer(
        repository=repository,
    )

    await service.handle(
        {
            "resourceId": "res-2",
            "triggerSource": "TAG_CHANGED",
        }
    )

    assert repository.load_calls == ["res-2"]
    assert repository.saved is not None
    assert repository.saved.resource_id == "res-2"
    assert repository.saved.owner_id == "owner-2"


@pytest.mark.anyio
async def test_acl_projection_service_rejects_missing_resource_item() -> None:
    service = RagAclRecalculateConsumer(
        repository=_RecordingAclProjectionRepository(),
    )

    with pytest.raises(RagAclProjectionError):
        await service.handle(
            {
                "resourceId": "res-2",
                "triggerSource": "TAG_CHANGED",
            }
        )


@pytest.mark.anyio
async def test_mongo_acl_projection_repository_loads_resource_item_from_pymongo_collection(
        monkeypatch,
) -> None:
    raw_resource = {
        "_id": "res-1",
        "ownerId": "owner-1",
        "specifiedUsersGrantedActionsMask": {"reader": 2},
        "computedGroupAcls": {},
    }
    collection = _FakeProjectionCollection(
        database={
            "wisepen_resource_items": _FakeResourceCollection(raw_resource),
        }
    )
    monkeypatch.setattr(
        RagAclProjectionDocument,
        "get_pymongo_collection",
        classmethod(lambda cls: collection),
    )
    repository = MongoRagAclProjectionRepository(
        projector=RagAclProjectionProjector(),
    )

    projection = await repository.load_resource_projection("res-1")

    assert projection is not None
    assert projection.resource_id == "res-1"
    assert projection.owner_id == "owner-1"
    assert projection.readable_users == ("reader",)
    assert collection.database["wisepen_resource_items"].queries == [{"_id": "res-1"}]


class _RecordingAclProjectionRepository:
    def __init__(self) -> None:
        self.load_calls: list[str] = []
        self.saved: RagResourceAclProjection | None = None
        self.source_projection: RagResourceAclProjection | None = None

    async def upsert_projection(self, projection: RagResourceAclProjection) -> None:
        self.saved = projection

    async def get_projection(self, resource_id: str) -> RagResourceAclProjection | None:
        if self.saved is None or self.saved.resource_id != resource_id:
            return None
        return self.saved

    async def load_resource_projection(self, resource_id: str) -> RagResourceAclProjection | None:
        self.load_calls.append(resource_id)
        if self.source_projection is None or self.source_projection.resource_id != resource_id:
            return None
        return self.source_projection


class _RecordingAclProjectionUpdater(RagAclProjectionUpdater):
    def __init__(self) -> None:
        self.updated: list[RagResourceAclProjection] = []

    async def update_read_acl(self, projection: RagResourceAclProjection) -> None:
        self.updated.append(projection)


class _FakeProjectionCollection:
    def __init__(self, *, database: dict[str, object]) -> None:
        self.database = database


class _FakeResourceCollection:
    def __init__(self, raw: dict[str, object] | None) -> None:
        self.raw = raw
        self.queries: list[dict[str, object]] = []

    async def find_one(self, query: dict[str, object]) -> dict[str, object] | None:
        self.queries.append(query)
        return self.raw
