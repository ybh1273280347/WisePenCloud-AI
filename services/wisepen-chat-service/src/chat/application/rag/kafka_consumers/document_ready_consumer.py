from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from chat.application.rag.ingestion.ingester import RagMarkdownIngester, RagMarkdownIngestResult
from chat.application.rag.ingestion.models import RagMarkdownIngestionPayload
from chat.application.rag.kafka_consumers._utils import read_required_string
from common.logger import info


class DocumentReadyMessageError(ValueError):
    """文档就绪事件 payload 不符合 RAG 入库要求。"""


class RagDocumentReadyConsumer:
    """消费文档就绪事件，并执行 RAG 入库主链路（分块 + embedding + 写入 Qdrant）。

    处理流程：
    1. 解析 Kafka 消息，提取 resourceId / version / content
    2. 构建 RagMarkdownIngestionPayload
    3. 调用 ingester 执行 Markdown 分块、向量化、写入
    """

    __slots__ = ("_ingester",)

    def __init__(
            self,
            *,
            ingester: RagMarkdownIngester,
    ) -> None:
        self._ingester = ingester

    async def handle(self, payload: Mapping[str, Any]) -> None:
        result = await self.ingest(payload)
        info(
            "rag document ready event consumed.",
            resource_id=result.resource_id,
            document_version=result.document_version,
            parent_chunk_count=len(result.parent_chunks),
            child_chunk_count=len(result.child_chunks),
            pipeline=result.pipeline,
        )

    async def ingest(self, payload: Mapping[str, Any]) -> RagMarkdownIngestResult:
        message = _parse_document_ready_message(payload)
        rag_payload = RagMarkdownIngestionPayload(
            resource_id=message.resource_id,
            document_version=message.version,
            markdown=message.content,
        )
        return await self._ingester.ingest_markdown(rag_payload)


@dataclass(frozen=True, slots=True)
class _DocumentReadyMessage:
    """Kafka 文档就绪消息的解析结果。"""

    content: str
    resource_id: str
    version: str


def _parse_document_ready_message(payload: Mapping[str, Any]) -> _DocumentReadyMessage:
    resource_id = read_required_string(
        payload,
        "resourceId",
        message_name="DocumentReadyMessage",
        error_factory=DocumentReadyMessageError,
    )
    version = read_required_string(
        payload,
        "version",
        message_name="DocumentReadyMessage",
        error_factory=DocumentReadyMessageError,
    )
    content = read_required_string(
        payload,
        "content",
        message_name="DocumentReadyMessage",
        error_factory=DocumentReadyMessageError,
    )
    return _DocumentReadyMessage(
        content=content,
        resource_id=resource_id,
        version=version,
    )
