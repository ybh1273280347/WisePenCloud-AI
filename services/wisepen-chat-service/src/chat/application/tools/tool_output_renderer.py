from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
from typing import Any

from dicttoxml import dicttoxml
from lxml import etree
from pydantic import BaseModel

from chat.application.tools.core.execution.result import ToolExecutionResult
from chat.application.tools.core.llm.renderer import RenderToolResult
from chat.application.tools.core.tool_return import ToolReturn

logging.getLogger("dicttoxml").setLevel(logging.WARNING)

_DEFAULT_ROOT_TAG = "result"
_XML_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*")


@dataclass(frozen=True, slots=True)
class RenderedToolOutput:
    """工具输出完成模型渲染后的中间结果。"""

    tool_name: str
    tool_call_id: str
    tool_arguments: dict[str, Any]
    root_tag: str
    visible_result: dict[str, Any]
    cacheable_texts: tuple[str, ...]
    rendered_text: str


class ToolOutputRenderer:
    """将任意工具返回值转为模型可读 XML。"""

    __slots__ = ()

    @staticmethod
    def render_result(*, tool_result: ToolExecutionResult) -> RenderedToolOutput:
        """渲染成功输出，不做缓存占位。"""
        invocation = tool_result.tool_invocation
        output = tool_result.tool_output

        if isinstance(output, ToolReturn):
            root_tag = _validate_xml_tag(output.tag)
            visible_result = _normalize_mapping(output.visible_result)
            cacheable_texts = tuple(map(str, output.cacheable_texts))
            rendered_text = render_tool_xml(
                root_tag=root_tag,
                payload=visible_result,
            )
        else:
            root_tag = _DEFAULT_ROOT_TAG
            visible_result, rendered_text = _render_regular_return(
                root_tag,
                output,
            )
            cacheable_texts = ()

        return RenderedToolOutput(
            tool_name=invocation.tool_name,
            tool_call_id=invocation.tool_call_id,
            tool_arguments=invocation.tool_call_arguments,
            root_tag=root_tag,
            visible_result=visible_result,
            cacheable_texts=cacheable_texts,
            rendered_text=rendered_text,
        )

    @staticmethod
    def render_error_result(*, tool_result: ToolExecutionResult) -> RenderToolResult:
        """渲染失败输出。错误内容不计入 ToolContentStore 缓存。"""
        invocation = tool_result.tool_invocation

        return RenderToolResult(
            tool_call_id=invocation.tool_call_id,
            tool_name=invocation.tool_name,
            persisted_output_placeholder=None,
            tool_output=render_tool_xml(
                root_tag=_DEFAULT_ROOT_TAG,
                payload=_error_payload(tool_result),
            ),
        )


def render_tool_xml(
        *,
        root_tag: str,
        payload: dict[str, Any],
        inline_contents: tuple[str, ...] = (),
        content_receipts: tuple[dict[str, Any], ...] = (),
) -> str:
    """将结构化工具结果渲染为 XML。"""
    root = _mapping_element(
        _validate_xml_tag(root_tag),
        _normalize_mapping(payload),
    )

    if inline_contents:
        contents = etree.SubElement(root, "contents")
        if len(inline_contents) == 1:
            contents.text = etree.CDATA(inline_contents[0])
        else:
            for content in inline_contents:
                item = etree.SubElement(contents, "item")
                item.text = etree.CDATA(content)

    if content_receipts:
        receipt_payload: Mapping[Any, Any] = (
            content_receipts[0]
            if len(content_receipts) == 1
            else {"items": content_receipts}
        )
        root.append(
            _mapping_element(
                "content_receipt",
                _normalize_mapping(receipt_payload),
            )
        )

    return _serialize(root)


def _render_regular_return(
        root_tag: str,
        value: Any,
) -> tuple[dict[str, Any], str]:
    normalized = _normalize(value)

    if isinstance(normalized, dict):
        return normalized, render_tool_xml(
            root_tag=root_tag,
            payload=normalized,
        )

    if isinstance(normalized, list):
        payload = {"items": normalized}
        return payload, render_tool_xml(
            root_tag=root_tag,
            payload=payload,
        )

    root = etree.Element(root_tag)
    if normalized is not None:
        root.text = (
            "true" if normalized
            else "false"
        ) if isinstance(normalized, bool) else str(normalized)

    return {}, _serialize(root)


def _mapping_element(
        root_tag: str,
        payload: dict[str, Any],
) -> etree._Element:
    xml = dicttoxml(
        payload,
        custom_root=root_tag,
        attr_type=False,
        item_func=lambda _: "item",
        xml_declaration=False,
    )
    return etree.fromstring(xml)


def _serialize(element: etree._Element) -> str:
    return etree.tostring(
        element,
        pretty_print=True,
        encoding="unicode",
    )


def _normalize_mapping(value: Mapping[Any, Any]) -> dict[str, Any]:
    return {
        str(key): normalized
        for key, item in value.items()
        if (normalized := _normalize(item)) is not None
    }


def _normalize(value: Any) -> Any:
    """将框架对象递归转换为 XML 可序列化基础类型。"""
    if isinstance(value, Enum):
        return _normalize(value.value)

    if isinstance(value, BaseModel):
        return _normalize(value.model_dump())

    if is_dataclass(value) and not isinstance(value, type):
        return _normalize(asdict(value))

    if isinstance(value, Mapping):
        return _normalize_mapping(value)

    if isinstance(value, list | tuple):
        return [
            normalized
            for item in value
            if (normalized := _normalize(item)) is not None
        ]

    if isinstance(value, str | int | float | bool) or value is None:
        return value

    return str(value)


def _error_payload(
        tool_result: ToolExecutionResult,
) -> dict[str, Any]:
    error = tool_result.tool_execution_error

    if error is None:
        return {
            "error": {
                "reason": "unknown_tool_error",
                "retryable": False,
                "metadata": {},
            }
        }

    return _normalize_mapping({
        "error": {
            "reason": error.reason,
            "detail_reason": error.detail_reason,
            "retryable": error.retryable,
            "metadata": error.metadata,
        }
    })


def _validate_xml_tag(tag: str) -> str:
    if not tag or _XML_NAME_RE.fullmatch(tag) is None:
        raise ValueError(f"Invalid XML root tag: {tag!r}")
    return tag