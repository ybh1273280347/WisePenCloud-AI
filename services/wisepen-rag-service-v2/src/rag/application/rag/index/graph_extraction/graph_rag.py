"""QueryClient 与 Neo4j GraphRAG SDK 的适配。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from neo4j_graphrag.experimental.components.entity_relation_extractor import (
    LLMEntityRelationExtractor,
    OnError,
)
from neo4j_graphrag.experimental.components.schema import GraphSchema
from neo4j_graphrag.experimental.components.types import (
    Neo4jGraph,
    TextChunk,
    TextChunks,
)
from neo4j_graphrag.llm.base import LLMInterfaceV2
from neo4j_graphrag.llm.types import LLMResponse
from neo4j_graphrag.types import LLMMessage
from pydantic import BaseModel

from .windows import KnowledgeExtractionWindow, render_extraction_window

if TYPE_CHECKING:
    from rag.utils.llm_clients.query import QueryClient


class QueryClientGraphRagLLM(LLMInterfaceV2):
    """将项目 QueryClient 适配为 GraphRAG 的结构化输出接口。"""

    supports_structured_output = True

    def __init__(self, *, client: QueryClient) -> None:
        super().__init__(model_name=client.model)
        self._client = client

    @property
    def cache_profile(self) -> str:
        return f"{self._client.model}:{self._client.thinking or 'default'}"

    def invoke(
        self,
        input: list[LLMMessage],
        *,
        response_format: type[BaseModel] | dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        del kwargs
        prompt, messages = _query_messages(input)
        result = self._client.query(
            prompt,
            messages=messages,
            response_format=_response_format(response_format),
        )
        return LLMResponse(content=result.content)

    async def ainvoke(
        self,
        input: list[LLMMessage],
        *,
        response_format: type[BaseModel] | dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        del kwargs
        prompt, messages = _query_messages(input)
        result = await self._client.aquery(
            prompt,
            messages=messages,
            response_format=_response_format(response_format),
        )
        return LLMResponse(content=result.content)


class GraphRagCandidateExtractor:
    """调用 GraphRAG SDK，从一组业务窗口生成未经发布的候选图。"""

    __slots__ = ("_extractor",)

    def __init__(self, *, llm: LLMInterfaceV2, max_concurrency: int) -> None:
        self._extractor = LLMEntityRelationExtractor(
            llm=llm,  # type: ignore[arg-type]
            create_lexical_graph=False,
            on_error=OnError.RAISE,
            max_concurrency=max_concurrency,
            use_structured_output=True,
        )

    async def extract(
        self,
        windows: list[KnowledgeExtractionWindow],
        schema: GraphSchema,
    ) -> Neo4jGraph:
        return await self._extractor.run(
            chunks=TextChunks(
                chunks=[
                    TextChunk(
                        uid=window.window_id,
                        index=window.ordinal,
                        text=render_extraction_window(window),
                        metadata={
                            "resource_id": window.resource_id,
                            "content_revision": window.content_revision,
                        },
                    )
                    for window in windows
                ]
            ),
            schema=schema,
        )


def _query_messages(input: list[LLMMessage]) -> tuple[str, list[dict[str, Any]]]:
    if not input:
        raise ValueError("GraphRAG LLM input must contain at least one message")
    messages = [
        {
            "role": str(message.get("role") or "user"),
            "content": str(message.get("content") or ""),
        }
        for message in input
    ]
    return str(messages.pop()["content"]), messages


def _response_format(
    value: type[BaseModel] | dict[str, Any] | None,
) -> dict[str, Any] | None:
    if value is None or isinstance(value, dict):
        return value
    return {
        "type": "json_schema",
        "json_schema": {
            "name": value.__name__,
            "schema": value.model_json_schema(),
        },
    }
