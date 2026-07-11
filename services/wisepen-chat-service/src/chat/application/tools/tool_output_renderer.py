from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime, time
from enum import Enum
from typing import Any
from uuid import UUID

import orjson
from pydantic import BaseModel

from chat.application.tools.core.execution.result import ToolExecutionResult
from chat.application.tools.core.llm.renderer import RenderToolResult
from chat.application.tools.core.tool_return import ToolReturn


_JSON_OPTIONS = orjson.OPT_NON_STR_KEYS | orjson.OPT_SERIALIZE_NUMPY
_NATIVE_KEY_TYPES = (str, int, float, bool, datetime, date, time, Enum, UUID)


@dataclass(frozen=True, slots=True)
class RenderedToolOutput:
    """工具输出完成模型渲染后的中间结果。"""

    tool_name: str
    tool_call_id: str
    tool_arguments: dict[str, Any]
    result_tag: str
    visible_result: dict[str, Any]
    cacheable_texts: tuple[str, ...]
    rendered_text: str


class ToolOutputRenderer:
    """将任意工具返回值转为模型可读的紧凑 JSON 或文本。"""

    __slots__ = ()

    @staticmethod
    def render_result(*, tool_result: ToolExecutionResult) -> RenderedToolOutput:
        invocation = tool_result.tool_invocation
        output = tool_result.tool_output

        if isinstance(output, ToolReturn):
            visible_result = dict(output.visible_result)
            cacheable_texts = tuple(map(str, output.cacheable_texts))
            result_tag = output.tag
            render_value = visible_result
        else:
            visible_result = output if isinstance(output, dict) else {}
            cacheable_texts = ()
            result_tag = "result"
            render_value = output

        return RenderedToolOutput(
            tool_name=invocation.tool_name,
            tool_call_id=invocation.tool_call_id,
            tool_arguments=invocation.tool_call_arguments,
            result_tag=result_tag,
            visible_result=visible_result,
            cacheable_texts=cacheable_texts,
            rendered_text=render_tool_output(render_value),
        )

    @staticmethod
    def render_error_result(*, tool_result: ToolExecutionResult) -> RenderToolResult:
        invocation = tool_result.tool_invocation
        error = tool_result.tool_execution_error

        payload = {
            "error": {
                "reason": error.reason if error else "unknown_tool_error",
                "detail_reason": error.detail_reason if error else None,
                "retryable": error.retryable if error else False,
                "metadata": error.metadata if error else {},
            }
        }

        return RenderToolResult(
            tool_call_id=invocation.tool_call_id,
            tool_name=invocation.tool_name,
            persisted_output_placeholder=None,
            tool_output=render_tool_output(payload),
        )


def render_tool_output(value: Any) -> str:
    """优先输出紧凑 JSON，必要时归一化容器，最终退回文本。"""
    try:
        return _encode_json(value)
    except Exception:
        pass

    try:
        return _encode_json(_normalize_json(value))
    except Exception:
        return _safe_text(value)


def build_tool_result_payload(
        visible_result: Mapping[str, Any],
        *,
        inline_contents: tuple[str, ...] = (),
        content_receipts: tuple[dict[str, Any], ...] = (),
) -> dict[str, Any]:
    """将运行时托管内容附加到工具可见结果。"""
    payload = dict(visible_result)
    if inline_contents:
        payload["contents"] = inline_contents
    if content_receipts:
        payload["content_receipts"] = content_receipts
    return payload


def _encode_json(value: Any) -> str:
    return orjson.dumps(
        value,
        default=_json_default,
        option=_JSON_OPTIONS,
    ).decode()


def _json_default(value: Any) -> Any:
    """处理常见非原生 value，其余直接文本化。"""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, (set, frozenset)):
        return list(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).decode(errors="replace")
    return _safe_text(value)


def _normalize_json(value: Any) -> Any:
    """递归归一化容器，并将不受支持的 Mapping key 转成文本。"""
    if isinstance(value, BaseModel):
        return _normalize_json(value.model_dump(mode="json"))

    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _normalize_json(getattr(value, field.name))
            for field in fields(value)
        }

    if isinstance(value, Mapping):
        return {
            _normalize_key(key): _normalize_json(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set, frozenset)):
        return [_normalize_json(item) for item in value]

    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).decode(errors="replace")

    return value


def _normalize_key(key: Any) -> Any:
    """保留 orjson 原生 key，其余 key 统一转成安全文本。"""
    if key is None or isinstance(key, _NATIVE_KEY_TYPES):
        return key
    if isinstance(key, (bytes, bytearray, memoryview)):
        return bytes(key).decode(errors="replace")
    return _safe_text(key)


def _safe_text(value: Any) -> str:
    try:
        text = str(value)
    except Exception:
        text = f"<unrenderable {type(value).__qualname__}>"
    return text.encode(errors="replace").decode()
