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
    def __init__(self, *, content: str, raw: object, usage_tokens: int = 0) -> None:
        self.content = content
        self.raw = raw
        self.usage_tokens = usage_tokens


class AdapterQueryClient:
    pass


def build_query_client():
    raise AssertionError("test should inject a fake query client")


llm_clients_module.AdapterQueryClient = AdapterQueryClient
llm_clients_module.QueryResult = QueryResult
llm_clients_module.build_query_client = build_query_client
sys.modules["chat.application.utils.llm_clients"] = llm_clients_module

from chat.application.rag.ingestion.context_indexing import (
    ContextIndexingError,
    ContextIndexingService,
)
from chat.application.rag.ingestion.models import ContextIndexingInput


class _FakeClient:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[dict[str, object]] = []

    async def aquery(self, **kwargs):
        self.calls.append(kwargs)
        return QueryResult(content=self.content, raw={}, usage_tokens=17)


@pytest.mark.anyio
async def test_context_indexing_service_uses_llm_json_payload() -> None:
    client = _FakeClient(
        '{"context_summary": "说明 Redis 淘汰策略的作用范围", '
        '"important_terms": ["Redis", "volatile-lru", "maxmemory-policy"]}'
    )
    service = ContextIndexingService(client=client)

    result = await service.build(
        ContextIndexingInput(
            parent_text=(
                "Redis 内存管理章节介绍 maxmemory-policy，"
                "其中 volatile-lru 只影响设置过期时间的 key。"
            ),
            child_text="volatile-lru 只淘汰设置了过期时间的 key。",
            document_title="Redis 运维手册",
            section_path=("内存管理",),
        )
    )

    assert result.usage_tokens == 17
    assert result.context_summary == "说明 Redis 淘汰策略的作用范围"
    assert result.important_terms == ("Redis", "volatile-lru", "maxmemory-policy")
    assert "重要术语: Redis、volatile-lru、maxmemory-policy" in result.indexing_text
    assert "Redis 内存管理章节介绍 maxmemory-policy" in client.calls[0]["prompt"]


@pytest.mark.anyio
async def test_context_indexing_service_rejects_bad_llm_response() -> None:
    service = ContextIndexingService(client=_FakeClient("not json"))

    with pytest.raises(ContextIndexingError):
        await service.build(
            ContextIndexingInput(
                parent_text="鉴权章节说明 API 请求需要携带访问凭证。",
                child_text="请求必须携带 Authorization header。",
                document_title="API 文档",
                section_path=("鉴权",),
            )
        )


@pytest.mark.anyio
async def test_context_indexing_service_requires_parent_text() -> None:
    client = _FakeClient('{"context_summary": "说明鉴权请求头要求", "important_terms": []}')
    service = ContextIndexingService(client=client)

    result = await service.build(
        ContextIndexingInput(
            parent_text="鉴权章节说明 API 请求需要携带访问凭证。",
            child_text="请求必须携带 Authorization header。",
            document_title="API 文档",
            section_path=("鉴权",),
        )
    )

    assert result.context_summary == "说明鉴权请求头要求"
    assert "鉴权章节说明 API 请求需要携带访问凭证。" in client.calls[0]["prompt"]
