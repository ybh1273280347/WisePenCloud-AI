from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from chat.application.tools.core import (
    ToolDefinition,
    ToolExecutionError,
    ToolLLMSpec,
    ToolParametersSchema,
    ToolPolicy,
    ToolRiskLevel,
    ToolSelectionMode,
    ToolUISpec,
)
from chat.application.tools.core.output_cache.cache_store import get_tool_content
from chat.core.config.app_settings import settings

_TIMEOUT_SECONDS = 300.0
_PARAMETERS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "content_id": {
            "type": "string",
            "minLength": 1,
            "description": "Required. One cached tool output content_id returned in a previous tool result.",
        },
        "start": {
            "type": "integer",
            "description": (
                "Optional inclusive character offset. Negative values count from the end."
            ),
        },
        "end": {
            "type": "integer",
            "description": (
                "Optional exclusive character offset. Negative values count from the end."
            ),
        },
    },
    "required": ["content_id"],
    "additionalProperties": False,
}


@dataclass(slots=True)
class CachedToolOutputWindow:
    """受单页字符预算限制的原文区间；偏移是半开字符坐标。"""

    text: str
    start_offset: int
    end_offset: int
    truncated: bool = False


@dataclass(slots=True)
class CachedToolOutputReadByRangeResult:
    content_id: str
    window: CachedToolOutputWindow | None = None
    reason: str | None = None


class CachedToolOutputReadByRangeTool:
    def __init__(self) -> None:
        self._definition = ToolDefinition(
            llm_spec=ToolLLMSpec(
                name="read_cached_tool_output_by_range",
                description=(
                    "Read source text from one cached tool output content_id by character range.\n\n"
                    "WHEN TO TRIGGER:\n"
                    "  - MUST trigger when you already know the exact offset range, the beginning, "
                    "or the end of cached tool output.\n"
                    "  - SHOULD trigger after structure/search results expose useful offsets.\n"
                    "DO NOT TRIGGER when:\n"
                    "  - You need sections; use read_cached_tool_output_by_section.\n"
                    "  - You need exact pattern matches; use search_cached_tool_output_by_regex.\n\n"
                    "INPUT RULES:\n"
                    "  - Ranges use Python slice semantics: start is inclusive and end is exclusive.\n"
                    "  - Negative offsets count from the end; start=-1000 reads the final 1000 characters.\n"
                    "  - Omitting both offsets reads from the beginning.\n"
                    "  - A single read is limited to the configured character budget; if truncated, "
                    "continue from the returned end_offset."
                ),
                parameters_schema=ToolParametersSchema(_PARAMETERS_SCHEMA),
            ),
            policy=_policy(),
            ui_spec=ToolUISpec(
                display_name="按范围读取缓存的工具输出",
                description="按字符偏移读取缓存工具输出片段，适合精确续读或展开搜索命中的上下文。",
            ),
        )

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    async def execute(
        self,
        context: dict[str, Any],
        config: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> CachedToolOutputReadByRangeResult:
        del config
        try:
            content_id = kwargs["content_id"]
            # 只允许读取当前会话持有的 content，避免 LLM 猜测其他会话的 content_id。
            stored = await get_tool_content(
                content_id=content_id,
                session_id=context["session_id"],
            )
            if stored is None:
                # content 不存在时返回普通结果，让 LLM 可以改用 structure/search 重新定位。
                return CachedToolOutputReadByRangeResult(
                    content_id=content_id,
                    reason="cached_tool_output_not_found",
                )
            return CachedToolOutputReadByRangeResult(
                content_id=content_id,
                window=_read_range(
                    stored.text,
                    start=kwargs.get("start"),
                    end=kwargs.get("end"),
                    char_budget=settings.TOOL_CONTENT_READ_WINDOW_CHAR_BUDGET,
                ),
            )
        except Exception as exc:
            raise ToolExecutionError(
                reason="read_cached_tool_output_by_range_failed",
                detail_reason=str(exc),
                retryable=False,
            ) from exc


def _policy() -> ToolPolicy:
    return ToolPolicy(
        expose_by_default=False,
        selection_mode=ToolSelectionMode.CONTEXTUAL,
        persist_output=True,
        risk_level=ToolRiskLevel.LOW,
        required_context_keys=("session_id",),
        timeout_seconds=_TIMEOUT_SECONDS,
    )


def _normalize_offset(value: int | None, text_length: int, *, default: int) -> int:
    """把 Python 切片偏移规范到原文范围内。"""
    offset = default if value is None else value
    if offset < 0:
        offset += text_length
    return min(max(offset, 0), text_length)


def _read_range(
    text: str,
    *,
    start: int | None,
    end: int | None,
    char_budget: int,
) -> CachedToolOutputWindow:
    """按原文坐标读取请求区间，并限制单次返回字符数。"""
    normalized_start = _normalize_offset(start, len(text), default=0)
    requested_end = _normalize_offset(end, len(text), default=len(text))
    normalized_end = min(
        max(requested_end, normalized_start),
        normalized_start + char_budget,
    )
    return CachedToolOutputWindow(
        text=text[normalized_start:normalized_end],
        start_offset=normalized_start,
        end_offset=normalized_end,
        truncated=requested_end > normalized_end,
    )
