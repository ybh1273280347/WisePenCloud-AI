from __future__ import annotations

import json
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
_LOGGER = logging.getLogger(__name__)

_DEFAULT_ROOT_TAG = "result"
_XML_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*")
_INVALID_XML_CHAR_RE = re.compile(
    r"[^\x09\x0A\x0D\x20-\uD7FF\uE000-\uFFFD\U00010000-\U0010FFFF]"
)


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

        root_tag = _DEFAULT_ROOT_TAG
        visible_result: dict[str, Any] = {}
        cacheable_texts: tuple[str, ...] = ()

        try:
            if isinstance(output, ToolReturn):
                root_tag = _validate_xml_tag(output.tag)
                visible_result = _normalize_mapping(output.visible_result)
                cacheable_texts = tuple(map(str, output.cacheable_texts))
                rendered_text = render_tool_xml(
                    root_tag=root_tag,
                    payload=visible_result,
                )
            else:
                visible_result, rendered_text = _render_regular_return(output)
        except Exception as exc:
            _LOGGER.warning(
                "tool output rendering failed; returning raw result.",
                exc_info=exc,
            )

            root_tag = _DEFAULT_ROOT_TAG
            visible_result = {}
            cacheable_texts = ()

            rendered_text = _raw_result_text(
                output.visible_result
                if isinstance(output, ToolReturn)
                else output,
                inline_contents=(
                    tuple(map(str, output.cacheable_texts))
                    if isinstance(output, ToolReturn)
                    else ()
                ),
            )

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
        error = tool_result.tool_execution_error

        if error is None:
            payload = {
                "error": {
                    "reason": "unknown_tool_error",
                    "retryable": False,
                    "metadata": {},
                }
            }
        else:
            payload = {
                "error": {
                    "reason": error.reason,
                    "detail_reason": error.detail_reason,
                    "retryable": error.retryable,
                    "metadata": error.metadata,
                }
            }

        return RenderToolResult(
            tool_call_id=invocation.tool_call_id,
            tool_name=invocation.tool_name,
            persisted_output_placeholder=None,
            tool_output=render_tool_xml(
                root_tag=_DEFAULT_ROOT_TAG,
                payload=payload,
            ),
        )


def render_tool_xml(
        *,
        root_tag: str,
        payload: Mapping[Any, Any],
        inline_contents: tuple[str, ...] = (),
        content_receipts: tuple[dict[str, Any], ...] = (),
) -> str:
    """将结构化工具结果渲染为 XML。"""
    try:
        root = _mapping_element(
            _validate_xml_tag(root_tag),
            _normalize_mapping(payload),
        )

        if inline_contents:
            contents = etree.SubElement(root, "contents")

            if len(inline_contents) == 1:
                contents.text = etree.CDATA(
                    _sanitize_xml_text(inline_contents[0])
                )
            else:
                for content in inline_contents:
                    item = etree.SubElement(contents, "item")
                    item.text = etree.CDATA(_sanitize_xml_text(content))

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
    except Exception as exc:
        _LOGGER.warning(
            "tool XML rendering failed; returning raw result.",
            exc_info=exc,
        )
        return _raw_result_text(
            payload,
            inline_contents=inline_contents,
            content_receipts=content_receipts,
        )


def _render_regular_return(value: Any) -> tuple[dict[str, Any], str]:
    normalized = _normalize(value)

    if isinstance(normalized, list):
        normalized = {"items": normalized}

    if isinstance(normalized, dict):
        return normalized, render_tool_xml(
            root_tag=_DEFAULT_ROOT_TAG,
            payload=normalized,
        )

    root = etree.Element(_DEFAULT_ROOT_TAG)

    if normalized is not None:
        root.text = (
            str(normalized).lower()
            if isinstance(normalized, bool)
            else str(normalized)
        )

    return {}, _serialize(root)


def _mapping_element(
        tag: str,
        payload: Mapping[str, Any],
) -> etree._Element:
    return etree.fromstring(
        dicttoxml(
            payload,
            custom_root=tag,
            attr_type=False,
            item_func=lambda _: "item",
            xml_declaration=False,
        )
    )


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

    if isinstance(value, (list, tuple)):
        return [
            normalized
            for item in value
            if (normalized := _normalize(item)) is not None
        ]

    if isinstance(value, str):
        return _sanitize_xml_text(value)

    if isinstance(value, (int, float, bool)) or value is None:
        return value

    return _sanitize_xml_text(str(value))


def _validate_xml_tag(tag: str) -> str:
    if not tag or _XML_NAME_RE.fullmatch(tag) is None:
        raise ValueError(f"Invalid XML root tag: {tag!r}")
    return tag


def _sanitize_xml_text(text: str) -> str:
    return _INVALID_XML_CHAR_RE.sub("", text)


def _raw_result_text(
        payload: Any,
        *,
        inline_contents: tuple[str, ...] = (),
        content_receipts: tuple[dict[str, Any], ...] = (),
) -> str:
    raw_result: dict[str, Any] = {"result": payload}

    if inline_contents:
        raw_result["contents"] = inline_contents

    if content_receipts:
        raw_result["content_receipts"] = content_receipts

    try:
        return json.dumps(
            raw_result,
            ensure_ascii=False,
            default=str,
            indent=2,
        )
    except Exception:
        return repr(raw_result)