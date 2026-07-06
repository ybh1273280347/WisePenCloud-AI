from __future__ import annotations

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from chat.application.rag.acl import (  # noqa: E402
    RagAclProjectionError,
    RagResourceAclProjection,
    parse_rag_acl_projection,
)
from chat.application.rag.consumers import (  # noqa: E402
    RagAclProjectionService,
    parse_acl_recalculate_message,
)


def test_parse_acl_recalculate_message_uses_real_resource_topic_fields() -> None:
    message = parse_acl_recalculate_message(
        {
            "resourceId": "res-1",
            "triggerSource": "TAG_CHANGED",
        }
    )

    assert message.resource_id == "res-1"
    assert message.trigger_source == "TAG_CHANGED"


def test_parse_rag_acl_projection_matches_resource_es_projection_shape() -> None:
    projection = parse_rag_acl_projection(
        {
            "resourceId": "res-1",
            "ownerId": "owner-1",
            "specifiedDiscoverUsers": ["user-a"],
            "computedGroupAcls": [
                {
                    "groupId": "101",
                    "isDiscover": True,
                    "specifiedUsers": ["blocked-user"],
                },
                {
                    "groupId": "102",
                    "isDiscover": False,
                    "specifiedUsers": ["allowed-user"],
                },
            ],
        }
    )

    assert projection.resource_id == "res-1"
    assert projection.owner_id == "owner-1"
    assert projection.specified_discover_users == ("user-a",)
    assert [item.group_id for item in projection.computed_group_acls] == ["101", "102"]
    assert projection.computed_group_acls[0].is_discover is True
    assert projection.computed_group_acls[1].specified_users == ("allowed-user",)


@pytest.mark.anyio
async def test_acl_projection_service_saves_projection_from_enriched_event() -> None:
    repository = _RecordingAclProjectionRepository()
    service = RagAclProjectionService(
        repository=repository,
    )

    await service.handle(
        {
            "resourceId": "res-1",
            "triggerSource": "RESOURCE_ACTION_PERMISSION_CHANGED",
            "ownerId": "owner-1",
            "specifiedDiscoverUsers": ["user-a"],
            "computedGroupAcls": [],
        }
    )

    assert repository.load_calls == []
    assert repository.saved is not None
    assert repository.saved.resource_id == "res-1"
    assert repository.saved.owner_id == "owner-1"


@pytest.mark.anyio
async def test_acl_projection_service_fetches_projection_for_recalc_event() -> None:
    repository = _RecordingAclProjectionRepository()
    source_projection = RagResourceAclProjection(
        resource_id="res-2",
        owner_id="owner-2",
        computed_group_acls=(),
    )
    repository.source_projection = source_projection
    service = RagAclProjectionService(
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
    service = RagAclProjectionService(
        repository=_RecordingAclProjectionRepository(),
    )

    with pytest.raises(RagAclProjectionError):
        await service.handle(
            {
                "resourceId": "res-2",
                "triggerSource": "TAG_CHANGED",
            }
        )


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
