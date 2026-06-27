from __future__ import annotations

import asyncio
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal

from beanie import PydanticObjectId

from chat.application.llm_provider_resolver import LLMProviderResolver
from chat.core.config.app_settings import settings
from chat.core.providers import (
    AnthropicAdapter,
    GeminiAdapter,
    LiteLLMAdapter,
    OpenAIAdapter,
    QwenAdapter,
)
from chat.domain.entities import ChatMessage, Role
from chat.domain.entities.model import Model, ModelFamily, ModelProviderMapping
from chat.domain.entities.provider import Provider, ProviderType
from chat.domain.interfaces.llm import LLMEventType, LLMStreamEvent
from chat.domain.repositories.model_repo import ModelRequestInfo

ChatRole = Literal["system", "user", "assistant", "tool"]
Message = dict[str, Any]


@dataclass(frozen=True)
class QueryResult:
    content: str
    raw: Any
    usage_tokens: int = 0


class AdapterQueryClient:
    """面向内部小模型任务的统一 LLM adapter 查询客户端。"""

    def __init__(
        self,
        model: str,
        *,
        api_base: str | None = None,
        api_key: str | None = None,
        provider_type: ProviderType = ProviderType.LITELLM_OPENAI_COMPATIBLE,
        model_family: ModelFamily = ModelFamily.GENERIC,
        temperature: float | None = 0.0,
        max_tokens: int | None = None,
        **default_runtime_options: Any,
    ) -> None:
        self.model = model
        self.api_base = api_base
        self.api_key = api_key
        self.provider_type = provider_type
        self.model_family = model_family
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.default_runtime_options = default_runtime_options
        self._resolver = LLMProviderResolver(
            qwen_adapter=QwenAdapter(),
            openai_adapter=OpenAIAdapter(),
            anthropic_adapter=AnthropicAdapter(),
            gemini_adapter=GeminiAdapter(),
            litellm_adapter=LiteLLMAdapter(),
        )

    async def aquery(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        messages: list[Message] | None = None,
        model: str | None = None,
        api_base: str | None = None,
        api_key: str | None = None,
        provider_type: ProviderType | str | None = None,
        model_family: ModelFamily | str | None = None,
        temperature: float | None = None,
        timeout: float | int | None = None,
        max_tokens: int | None = None,
        **runtime_options: Any,
    ) -> QueryResult:
        del timeout  # 统一 adapter 当前不暴露 per-call timeout，保留参数只为兼容旧调用点。
        request = self._build_model_request(
            model=model,
            api_base=api_base,
            api_key=api_key,
            provider_type=provider_type,
            model_family=model_family,
            temperature=temperature,
            max_tokens=max_tokens,
            runtime_options=runtime_options,
        )
        stream_events: list[LLMStreamEvent] = []
        content_parts: list[str] = []
        usage_tokens = 0
        provider = self._resolver.resolve(request)

        async for event in provider.stream_chat_completion(
            messages=self._build_messages(
                prompt=prompt,
                system_prompt=system_prompt,
                messages=messages,
            ),
            model_request=request,
            tools=None,
        ):
            stream_events.append(event)
            if event.type == LLMEventType.TEXT_DELTA and event.delta:
                content_parts.append(event.delta)
            elif event.type == LLMEventType.USAGE and event.usage:
                usage_tokens += event.usage.total_tokens

        return QueryResult(
            content="".join(content_parts),
            raw=stream_events,
            usage_tokens=usage_tokens,
        )

    def query(
        self,
        prompt: str,
        **kwargs: Any,
    ) -> QueryResult:
        """同步查询入口，用于少量非 async 调用场景。"""
        return asyncio.run(self.aquery(prompt, **kwargs))

    def _build_model_request(
        self,
        *,
        model: str | None,
        api_base: str | None,
        api_key: str | None,
        provider_type: ProviderType | str | None,
        model_family: ModelFamily | str | None,
        temperature: float | None,
        max_tokens: int | None,
        runtime_options: dict[str, Any],
    ) -> ModelRequestInfo:
        resolved_provider_type = _coerce_provider_type(provider_type) or self.provider_type
        resolved_model_family = (
            _coerce_model_family(model_family)
            or _infer_model_family(resolved_provider_type)
            or self.model_family
        )
        resolved_model_name = model or self.model
        resolved_runtime_options = dict(self.default_runtime_options)
        resolved_runtime_options.update(runtime_options)
        if temperature is not None:
            resolved_runtime_options["temperature"] = temperature
        elif self.temperature is not None:
            resolved_runtime_options.setdefault("temperature", self.temperature)

        output_tokens = max_tokens if max_tokens is not None else self.max_tokens
        provider = Provider(
            name="internal-query-provider",
            base_url=api_base if api_base is not None else self.api_base,
            api_key=api_key if api_key is not None else (self.api_key or ""),
            type=resolved_provider_type,
        )
        model_entity = Model(
            display_name=resolved_model_name,
            model_family=resolved_model_family,
            support_tools=False,
            max_output_tokens=output_tokens,
        )
        mapping = ModelProviderMapping(
            model_id=PydanticObjectId(),
            provider_id=PydanticObjectId(),
            provider_model_name=resolved_model_name,
        )
        return ModelRequestInfo(
            model=model_entity,
            mapping=mapping,
            provider=provider,
            runtime_options=resolved_runtime_options,
        )

    @staticmethod
    def _build_messages(
        *,
        prompt: str,
        system_prompt: str | None,
        messages: list[Message] | None,
    ) -> list[ChatMessage]:
        result: list[ChatMessage] = []
        if system_prompt:
            result.append(ChatMessage(session_id="", role=Role.SYSTEM, content=system_prompt))
        for message in messages or []:
            role = Role(str(message.get("role") or Role.USER.value))
            result.append(
                ChatMessage(
                    session_id="",
                    role=role,
                    content=str(message.get("content") or ""),
                )
            )
        result.append(ChatMessage(session_id="", role=Role.USER, content=prompt))
        return result


def _coerce_provider_type(value: ProviderType | str | None) -> ProviderType | None:
    if value is None:
        return None
    if isinstance(value, ProviderType):
        return value
    return ProviderType(value)


def _coerce_model_family(value: ModelFamily | str | None) -> ModelFamily | None:
    if value is None:
        return None
    if isinstance(value, ModelFamily):
        return value
    return ModelFamily(value)


def _infer_model_family(provider_type: ProviderType) -> ModelFamily | None:
    if provider_type == ProviderType.ALIBABA:
        return ModelFamily.QWEN
    if provider_type == ProviderType.OPENAI:
        return ModelFamily.GPT
    if provider_type == ProviderType.ANTHROPIC:
        return ModelFamily.CLAUDE
    if provider_type == ProviderType.GOOGLE:
        return ModelFamily.GEMINI
    return None


@lru_cache(maxsize=1)
def build_query_client() -> AdapterQueryClient:
    return AdapterQueryClient(
        model=settings.QUERY_MODEL,
        api_base=settings.LLM_BASE_URL,
        api_key=settings.LLM_API_KEY,
    )
