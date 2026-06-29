from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))


class _Settings:
    SUMMARY_MODEL = "test-summary-model"


config_module = types.ModuleType("chat.core.config.app_settings")
config_module.settings = _Settings()
sys.modules["chat.core.config.app_settings"] = config_module

llm_clients_module = types.ModuleType("chat.application.utils.llm_clients")


class QueryResult:
    def __init__(self, *, content: str, raw: object) -> None:
        self.content = content
        self.raw = raw


class LiteLLMQueryClient:
    pass


def build_query_client(**kwargs):
    raise AssertionError("test should inject a fake query client")


llm_clients_module.LiteLLMQueryClient = LiteLLMQueryClient
llm_clients_module.QueryResult = QueryResult
llm_clients_module.build_query_client = build_query_client
sys.modules["chat.application.utils.llm_clients"] = llm_clients_module

from chat.application.rag.ingestion.context_indexing import (
    ContextIndexingError,
    ContextIndexingService,
)
from chat.application.rag.ingestion.models import ContextIndexingInput, RagChildChunk


class _FakeClient:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[dict[str, object]] = []

    async def aquery(self, **kwargs):
        self.calls.append(kwargs)
        return QueryResult(content=self.content, raw={})


@pytest.mark.anyio
async def test_context_indexing_service_uses_llm_json_payload() -> None:
    client = _FakeClient(
        '{"indexing_context": "该片段说明 Redis volatile-lru 策略只作用于设置过期时间的 key。"}'
    )
    service = ContextIndexingService(client=client)

    result = await service.build(
        ContextIndexingInput(
            parent_text=(
                "Redis 内存管理章节介绍 maxmemory-policy，"
                "其中 volatile-lru 只影响设置过期时间的 key。"
            ),
            child_chunk=RagChildChunk(
                chunk_id="chunk-redis-1",
                text="volatile-lru 只淘汰设置了过期时间的 key。",
                chunk_index=1,
                parent_chunk_id="parent-redis",
                section_path=("内存管理",),
            ),
            document_title="Redis 运维手册",
        )
    )

    assert result.child_chunk.chunk_id == "chunk-redis-1"
    assert result.child_chunk.parent_chunk_id == "parent-redis"
    assert result.evidence_text == "volatile-lru 只淘汰设置了过期时间的 key。"
    assert result.indexing_context == "该片段说明 Redis volatile-lru 策略只作用于设置过期时间的 key。"
    assert result.child_chunk.indexing_context == result.indexing_context
    assert result.child_chunk.indexing_text == result.indexing_text
    assert "上下文补充: 该片段说明 Redis volatile-lru 策略只作用于设置过期时间的 key。" in result.indexing_text
    assert "正文: volatile-lru 只淘汰设置了过期时间的 key。" in result.indexing_text
    assert "<context_indexing_input>" in client.calls[0]["prompt"]
    assert "<document_title>Redis 运维手册</document_title>" in client.calls[0]["prompt"]
    assert "Redis 内存管理章节介绍 maxmemory-policy" in client.calls[0]["prompt"]


@pytest.mark.anyio
async def test_context_indexing_service_rejects_bad_llm_response() -> None:
    service = ContextIndexingService(client=_FakeClient("not json"))

    with pytest.raises(ContextIndexingError):
        await service.build(
            ContextIndexingInput(
                parent_text="鉴权章节说明 API 请求需要携带访问凭证。",
                child_chunk=RagChildChunk(
                    chunk_id="chunk-auth",
                    text="请求必须携带 Authorization header。",
                    chunk_index=1,
                    parent_chunk_id="parent-auth",
                    section_path=("鉴权",),
                ),
                document_title="API 文档",
            )
        )


@pytest.mark.anyio
async def test_context_indexing_service_requires_parent_text() -> None:
    client = _FakeClient('{"indexing_context": "该片段说明 API 鉴权请求头要求。"}')
    service = ContextIndexingService(client=client)

    result = await service.build(
        ContextIndexingInput(
            parent_text="鉴权章节说明 API 请求需要携带访问凭证。",
            child_chunk=RagChildChunk(
                chunk_id="chunk-auth",
                text="请求必须携带 Authorization header。",
                chunk_index=1,
                parent_chunk_id="parent-auth",
                section_path=("鉴权",),
            ),
            document_title="API 文档",
        )
    )

    assert result.indexing_context == "该片段说明 API 鉴权请求头要求。"
    assert "鉴权章节说明 API 请求需要携带访问凭证。" in client.calls[0]["prompt"]
