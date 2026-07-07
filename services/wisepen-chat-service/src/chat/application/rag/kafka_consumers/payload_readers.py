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
    if not isinstance(value, str):
        raise error_factory(f"{message_name}.{key} must be a string.")
    text = value.strip()
    if not text:
        raise error_factory(f"{message_name}.{key} must not be empty.")
    return text


def read_optional_string(payload: Mapping[str, Any], key: str) -> str | None:
    """从 Kafka 消息 payload 中读取可选字符串字段，缺失返回 None，空白返回 None。"""
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def read_required_version(
        payload: Mapping[str, Any],
        key: str,
        *,
        message_name: str,
        error_factory: Callable[[str], Exception],
) -> str:
    """读取 Java Integer/string 版本标识，并统一转成 RAG 内部版本字符串。"""
    value = payload.get(key)
    if value is None:
        raise error_factory(f"{message_name}.{key} is required.")
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise error_factory(f"{message_name}.{key} must be an integer or string.")
    text = str(value).strip()
    if not text:
        raise error_factory(f"{message_name}.{key} must not be empty.")
    return text