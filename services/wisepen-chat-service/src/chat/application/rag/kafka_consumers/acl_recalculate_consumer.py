from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from chat.application.rag.acl import (
    RagAclProjectionError,
    RagAclProjectionRepository,
    RagAclProjectionUpdater,
    RagResourceAclProjection,
)
from chat.application.rag.kafka_consumers.payload_readers import (
    read_optional_string,
    read_required_string,
)
from common.logger import info, warn


@dataclass(frozen=True, slots=True)
class AclRecalculateMessage:
    """Kafka ACL 重算消息的解析结果。"""

    resource_id: str
    trigger_source: str = ""


class RagAclRecalculateConsumer:
    """消费资源 ACL 重算事件，并刷新 RAG侧权限投影。

    处理流程：
    1. 解析 Kafka 消息，提取 resourceId
    2. 从 repository 回源查询 resource-service 原始数据并构建 VIEW/read 投影
    3. 持久化投影到 repository
    4. 通过 ACL updater 同步下游检索后端 payload
    """

    __slots__ = ("_repository", "_updater")

    def __init__(
            self,
            *,
            repository: RagAclProjectionRepository,
            updater: RagAclProjectionUpdater | None = None,
    ) -> None:
        self._repository = repository
        self._updater = updater

    async def handle(self, payload: Mapping[str, Any]) -> None:
        message = parse_acl_recalculate_message(payload)
        projection = await self.refresh_projection(message)
        if projection is None:
            warn(
                "rag acl projection refresh skipped because resource item was not found.",
                resource_id=message.resource_id,
                trigger_source=message.trigger_source,
            )
            return
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
    ) -> RagResourceAclProjection | None:
        projection = await self._repository.load_resource_projection(message.resource_id)
        if projection is None:
            return None
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
