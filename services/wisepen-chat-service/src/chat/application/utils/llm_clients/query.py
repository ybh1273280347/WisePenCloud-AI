from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import litellm

from chat.core.config.app_settings import settings

Message = dict[str, Any]


@dataclass(frozen=True)
class QueryResult:
    content: str
    raw: Any
    usage_tokens: int = 0


class LiteLLMQueryClient:
    """面向内部小模型任务的 LiteLLM 查询客户端。"""

    def __init__(
        self,
        model: str,
        *,
        api_base: str,
        api_key: str,
    ) -> None:
        self.model = model
        self.api_base = api_base
        self.api_key = api_key

    async def aquery(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        messages: list[Message] | None = None,
        max_tokens: int | None = None,
    ) -> QueryResult:
        response = await litellm.acompletion(
            **self._build_kwargs(
                prompt=prompt,
                system_prompt=system_prompt,
                messages=messages,
                max_tokens=max_tokens,
            )
        )
        return self._parse_response(response)

    def query(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        messages: list[Message] | None = None,
        max_tokens: int | None = None,
    ) -> QueryResult:
        """同步查询入口，用于少量非 async 调用场景。"""
        response = litellm.completion(
            **self._build_kwargs(
                prompt=prompt,
                system_prompt=system_prompt,
                messages=messages,
                max_tokens=max_tokens,
            )
        )
        return self._parse_response(response)

    def _build_kwargs(
        self,
        *,
        prompt: str,
        system_prompt: str | None,
        messages: list[Message] | None,
        max_tokens: int | None,
    ) -> dict[str, Any]:
        kw: dict[str, Any] = {
            "model": self.model,
            "messages": self._build_messages(
                prompt=prompt,
                system_prompt=system_prompt,
                messages=messages,
            ),
            "api_base": self.api_base,
            "api_key": self.api_key,
        }
        if max_tokens is not None:
            kw["max_tokens"] = max_tokens
        return kw

    @staticmethod
    def _build_messages(
        *,
        prompt: str,
        system_prompt: str | None,
        messages: list[Message] | None,
    ) -> list[Message]:
        result: list[Message] = []
        if system_prompt:
            result.append({"role": "system", "content": system_prompt})
        for message in messages or []:
            result.append(
                {
                    "role": str(message.get("role") or "user"),
                    "content": str(message.get("content") or ""),
                }
            )
        result.append({"role": "user", "content": prompt})
        return result

    @staticmethod
    def _parse_response(response: Any) -> QueryResult:
        choices = _get_value(response, "choices", []) or []
        content = ""
        if choices:
            first_choice = choices[0]
            message = _get_value(first_choice, "message")
            content = str(_get_value(message, "content", "") or "")
        usage = _get_value(response, "usage")
        usage_tokens = int(_get_value(usage, "total_tokens", 0) or 0) if usage is not None else 0
        return QueryResult(
            content=content,
            raw=response,
            usage_tokens=usage_tokens,
        )

@lru_cache(maxsize=8)
def build_query_client(*, model: str) -> LiteLLMQueryClient:
    return LiteLLMQueryClient(
        model=model,
        api_base=settings.LLM_BASE_URL,
        api_key=settings.LLM_API_KEY,
    )


def _get_value(source: Any, key: str, default: Any = None) -> Any:
    return source.get(key, default) if isinstance(source, dict) else getattr(source, key, default)
