from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from common.logger import info

from chat.application.rag.acl import (
    RagAclProjectionError,
    RagAclProjectionProjector,
    RagAclProjectionRepository,
    RagAclProjectionUpdater,
    RagResourceAclProjection,
)
from chat.application.rag.kafka_consumers._utils import (
    read_optional_string,
    read_required_string,
)


@dataclass(frozen=True, slots=True)
class AclRecalculateMessage:
    """Kafka ACL 重算消息的解析结果。"""

    resource_id: str
    trigger_source: str = ""


class RagAclRecalculateConsumer:
    """消费资源 ACL 重算事件，并刷新 RAG侧权限投影。

    处理流程：
    1. 解析 Kafka 消息，提取 resourceId
    2. 若消息已携带投影数据 → 直接构建投影（快速路径）
    3. 否则 → 从 repository 回源查询 resource-service 原始数据再构建投影
    4. 持久化投影到 repository
    5. 通过 ACL updater 同步下游检索后端 payload
    """

    __slots__ = ("_projector", "_repository", "_updater")

    def __init__(
            self,
            *,
            projector: RagAclProjectionProjector,
            repository: RagAclProjectionRepository,
            updater: RagAclProjectionUpdater | None = None,
    ) -> None:
        self._projector = projector
        self._repository = repository
        self._updater = updater

    async def handle(self, payload: Mapping[str, Any]) -> None:
        message = parse_acl_recalculate_message(payload)
        projection = await self.refresh_projection(message, payload)
        info(
            "rag acl projection refreshed.",
            resource_id=projection.resource_id,
            trigger_source=message.trigger_source,
            group_acl_count=len(projection.computed_group_acls),
            readable_user_count=len(projection.readable_users),
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
        if self._updater is not None:
            await self._updater.update_read_acl(projection)
        return projection


def parse_acl_recalculate_message(payload: Mapping[str, Any]) -> AclRecalculateMessage:
    resource_id = read_required_string(
        payload,
        "resourceId",
        message_name="AclRecalculateMessage",
        error_factory=RagAclProjectionError,
    )
    trigger_source = read_optional_string(payload, "triggerSource") or ""
    return AclRecalculateMessage(
        resource_id=resource_id,
        trigger_source=trigger_source,
    )
