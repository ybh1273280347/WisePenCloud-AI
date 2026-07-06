from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from common.logger import info

from chat.application.rag.acl import (
    RagAclProjectionError,
    RagAclProjectionProjector,
    RagAclProjectionRepository,
    RagResourceAclProjection,
)


@dataclass(frozen=True, slots=True)
class AclRecalculateMessage:
    resource_id: str
    trigger_source: str = ""


class RagAclRecalculateConsumer:
    """消费资源 ACL 重算事件，并刷新 RAG 侧权限投影。"""

    __slots__ = ("_projector", "_repository")

    def __init__(
            self,
            *,
            projector: RagAclProjectionProjector,
            repository: RagAclProjectionRepository,
    ) -> None:
        self._projector = projector
        self._repository = repository

    async def handle(self, payload: Mapping[str, Any]) -> None:
        message = parse_acl_recalculate_message(payload)
        projection = await self.refresh_projection(message, payload)
        info(
            "rag acl projection refreshed.",
            resource_id=projection.resource_id,
            trigger_source=message.trigger_source,
            group_acl_count=len(projection.computed_group_acls),
            specified_user_count=len(projection.specified_discover_users),
        )

    async def refresh_projection(
            self,
            message: AclRecalculateMessage,
            payload: Mapping[str, Any],
    ) -> RagResourceAclProjection:
        projection_payload = (
            payload
            if self._projector.has_projection_payload(payload)
            else None
        )
        projection = (
            self._projector.from_projection_payload(projection_payload)
            if projection_payload is not None
            else await self._repository.load_resource_projection(message.resource_id)
        )
        if projection is None:
            raise RagAclProjectionError("Resource item for ACL projection was not found.")
        if projection.resource_id != message.resource_id:
            raise RagAclProjectionError("ACL projection resourceId does not match recalculate message.")
        await self._repository.upsert_projection(projection)
        return projection


def parse_acl_recalculate_message(payload: Mapping[str, Any]) -> AclRecalculateMessage:
    resource_id = _read_required_string(payload, "resourceId")
    trigger_source = _read_optional_string(payload, "triggerSource") or ""
    return AclRecalculateMessage(
        resource_id=resource_id,
        trigger_source=trigger_source,
    )


def _read_required_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if value is None:
        raise RagAclProjectionError(f"AclRecalculateMessage.{key} is required.")
    text = str(value).strip()
    if not text:
        raise RagAclProjectionError(f"AclRecalculateMessage.{key} must not be empty.")
    return text


def _read_optional_string(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None
