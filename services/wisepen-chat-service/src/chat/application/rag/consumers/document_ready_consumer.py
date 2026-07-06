from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from common.logger import info

from chat.application.rag.ingestion import RagChunkingService
from chat.application.rag.ingestion.models import RagChunkingResult, RagMarkdownIngestionPayload


class DocumentReadyMessageError(ValueError):
    """文档就绪事件 payload 不符合 RAG 入库要求。"""


class RagDocumentReadyConsumer:
    """消费文档就绪事件，并把文档内容投影成 RAG 分块结果。"""

    __slots__ = ("_chunking_service",)

    def __init__(
            self,
            *,
            chunking_service: RagChunkingService,
    ) -> None:
        self._chunking_service = chunking_service

    async def handle(self, payload: Mapping[str, Any]) -> None:
        result = self.ingest(payload)
        info(
            "rag document ready event consumed.",
            resource_id=result.resource_id,
            document_version=result.document_version,
            parent_chunk_count=len(result.parent_chunks),
            child_chunk_count=len(result.child_chunks),
            pipeline=result.pipeline,
        )

    def ingest(self, payload: Mapping[str, Any]) -> RagChunkingResult:
        message = _parse_document_ready_message(payload)
        rag_payload = RagMarkdownIngestionPayload(
            resource_id=message.resource_id,
            document_version=message.version,
            markdown=message.content,
        )
        return self._chunking_service.chunk_payload(rag_payload)


@dataclass(frozen=True, slots=True)
class _DocumentReadyMessage:
    content: str
    resource_id: str
    version: str


def _parse_document_ready_message(payload: Mapping[str, Any]) -> _DocumentReadyMessage:
    resource_id = _read_required_string(payload, "resourceId")
    version = _read_required_string(payload, "version")
    content = _read_required_string(payload, "content")
    return _DocumentReadyMessage(
        content=content,
        resource_id=resource_id,
        version=version,
    )


def _read_required_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if value is None:
        raise DocumentReadyMessageError(f"DocumentReadyMessage.{key} is required.")
    text = str(value).strip()
    if not text:
        raise DocumentReadyMessageError(f"DocumentReadyMessage.{key} must not be empty.")
    return text
