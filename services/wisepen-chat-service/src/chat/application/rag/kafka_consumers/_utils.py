from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any


def read_required_string(
        payload: Mapping[str, Any],
        key: str,
        *,
        message_name: str,
        error_factory: Callable[[str], Exception],
) -> str:
    """从 Kafka 消息 payload 中读取必填字符串字段，缺失或为空则抛出指定异常。"""
    value = payload.get(key)
    if value is None:
        raise error_factory(f"{message_name}.{key} is required.")
    text = str(value).strip()
    if not text:
        raise error_factory(f"{message_name}.{key} must not be empty.")
    return text


def read_optional_string(payload: Mapping[str, Any], key: str) -> str | None:
    """从 Kafka 消息 payload 中读取可选字符串字段，缺失返回 None，空白返回 None。"""
    value = payload.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None
