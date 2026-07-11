import pytest

from chat.application import token_counter as token_counter_module
from chat.application.token_counter import TokenCounter
from chat.domain.entities import ChatMessage, Role


@pytest.mark.asyncio
async def test_count_messages_uses_local_token_counter(monkeypatch) -> None:
    async def fail_remote_count_tokens(*args, **kwargs):
        raise AssertionError("remote CountTokens API should not be called")

    def local_token_counter(**kwargs):
        assert kwargs["model"] == "openai/gpt-4o"
        assert kwargs["messages"] == [{"role": "user", "content": "hello"}]
        return 7

    async def run_in_thread(func, /, *args, **kwargs):
        assert func is local_token_counter
        return func(*args, **kwargs)

    monkeypatch.setattr(token_counter_module.litellm, "acount_tokens", fail_remote_count_tokens)
    monkeypatch.setattr(token_counter_module.litellm, "token_counter", local_token_counter)
    monkeypatch.setattr(token_counter_module.asyncio, "to_thread", run_in_thread)

    result = await TokenCounter().count_messages([
        ChatMessage.model_construct(session_id="session-1", role=Role.USER, content="hello"),
    ])

    assert result == 7


@pytest.mark.asyncio
async def test_count_text_uses_threaded_local_token_counter(monkeypatch) -> None:
    def local_token_counter(**kwargs):
        assert kwargs["model"] == "openai/gpt-4o"
        assert kwargs["text"] == "hello"
        return 3

    async def run_in_thread(func, /, *args, **kwargs):
        assert func is local_token_counter
        return func(*args, **kwargs)

    monkeypatch.setattr(token_counter_module.litellm, "token_counter", local_token_counter)
    monkeypatch.setattr(token_counter_module.asyncio, "to_thread", run_in_thread)

    result = await TokenCounter().count_text("hello")

    assert result == 3
