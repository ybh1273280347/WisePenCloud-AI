from __future__ import annotations

from typing import Any

from neo4j_graphrag.llm import LLMInterfaceV2
from neo4j_graphrag.llm.types import LLMResponse
from neo4j_graphrag.types import LLMMessage

from chat.application.utils.llm_clients import QueryClient


class WisePenGraphRagLLM(LLMInterfaceV2):
    """把 WisePen QueryClient 适配成 neo4j-graphrag V2 LLM 边界。"""

    supports_structured_output = True

    __slots__ = ("_client",)

    def __init__(self, client: QueryClient) -> None:
        super().__init__(model_name=client.model)
        self._client = client

    def invoke(
            self,
            input: list[LLMMessage],
            *,
            response_format: Any = None,
            **_: Any,
    ) -> LLMResponse:
        prompt, messages = _split_llm_messages(input)
        response = self._client.query(
            prompt,
            messages=messages,
            response_format={"type": "json_object"},
        )
        return LLMResponse(content=response.content)

    async def ainvoke(
            self,
            input: list[LLMMessage],
            *,
            response_format: Any = None,
            **_: Any,
    ) -> LLMResponse:
        prompt, messages = _split_llm_messages(input)
        response = await self._client.aquery(
            prompt,
            messages=messages,
            response_format={"type": "json_object"},
        )
        return LLMResponse(content=response.content)


def _split_llm_messages(messages: list[LLMMessage]) -> tuple[str, list[dict[str, str]]]:
    if not messages:
        return "", []

    history = [
        {
            "role": str(message.get("role") or "user"),
            "content": str(message.get("content") or ""),
        }
        for message in messages[:-1]
    ]
    prompt = str(messages[-1].get("content") or "")
    return prompt, history
