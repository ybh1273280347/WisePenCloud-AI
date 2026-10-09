from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import regex

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
from chat.application.tools.core.output_cache.cache_store import (
    StoredToolContent as StoredCachedToolOutput,
)
from chat.application.tools.core.output_cache.cache_store import get_tool_content

_MAX_REGEX_CHARS = 500
_MATCHES_PER_PAGE = 15
_REGEX_CONTEXT_CHARS = 200
_REGEX_SENTENCE_BOUNDARIES = frozenset(".。!?！？;；\n")
_SEARCH_TIMEOUT_SECONDS = 5
_TIMEOUT_SECONDS = 300.0

_PARAMETERS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "content_ids": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "minItems": 1,
            "maxItems": 16,
            "description": "Cached tool output content IDs, searched in the supplied order.",
        },
        "pattern": {
            "type": "string",
            "minLength": 1,
            "maxLength": _MAX_REGEX_CHARS,
            "description": "Python regular expression matched against the complete stored source text.",
        },
        "offset": {
            "type": "integer",
            "minimum": 0,
            "default": 0,
            "description": "Zero-based page number; each page contains at most 15 matches.",
        },
    },
    "required": ["content_ids", "pattern"],
    "additionalProperties": False,
}


@dataclass(slots=True)
class CachedToolOutputRegexHighlight:
    """窗口内命中位置；偏移相对窗口文本，使用字符半开区间。"""

    text: str
    start_offset: int
    end_offset: int


@dataclass(slots=True)
class CachedToolOutputRegexWindow:
    """一个或多个扩展上下文相交后形成的连续原文窗口。"""

    content_id: str
    text: str
    start_offset: int
    end_offset: int
    highlights: list[CachedToolOutputRegexHighlight]


@dataclass(slots=True)
class CachedToolOutputSearchByRegexResult:
    """一页正则命中及其上下文窗口。"""

    offset: int
    matched_count: int
    has_more: bool
    windows: list[CachedToolOutputRegexWindow] = field(default_factory=list)


class CachedToolOutputSearchByRegexTool:
    def __init__(self) -> None:
        self._definition = ToolDefinition(
            llm_spec=ToolLLMSpec(
                name="search_cached_tool_output_by_regex",
                description=(
                    "Search complete cached source texts with a Python regular expression. "
                    "Each page returns at most 15 exact matches. Use the zero-based offset "
                    "page number to continue while has_more is true. Each match gets up to "
                    "200 characters of nearby context, expanded toward sentence boundaries. "
                    "Contexts are merged only when their expanded ranges intersect. Window "
                    "start_offset and end_offset are absolute source offsets."
                ),
                parameters_schema=ToolParametersSchema(_PARAMETERS_SCHEMA),
            ),
            policy=_policy(),
            ui_spec=ToolUISpec(
                display_name="正则搜索缓存的工具输出",
                description="在缓存工具输出全文中按正则查找精确文本并分页返回上下文。",
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
    ) -> CachedToolOutputSearchByRegexResult:
        del config
        pattern = kwargs["pattern"]
        if len(pattern) > _MAX_REGEX_CHARS:
            raise ToolExecutionError(
                reason="regex_pattern_too_long",
                detail_reason=f"regex pattern is too long; max {_MAX_REGEX_CHARS} chars.",
            )
        try:
            regex.compile(pattern)
        except regex.error as exc:
            raise ToolExecutionError(
                reason="invalid_regex_pattern",
                detail_reason=str(exc),
            ) from exc

        try:
            offset = kwargs.get("offset", 0)
            if offset < 0:
                raise ValueError("offset must be a non-negative page number")
            stored_items = []
            session_id = context["session_id"]
            for content_id in dict.fromkeys(kwargs["content_ids"]):
                stored = await get_tool_content(
                    content_id=content_id,
                    session_id=session_id,
                )
                if stored is not None:
                    stored_items.append(stored)
            return await _search_by_regex(
                stored_items=stored_items,
                pattern=pattern,
                offset=offset,
            )
        except Exception as exc:
            raise ToolExecutionError(
                reason="search_cached_tool_output_by_regex_failed",
                detail_reason=str(exc),
                retryable=False,
            ) from exc


async def _search_by_regex(
    *,
    stored_items: Sequence[StoredCachedToolOutput],
    pattern: str,
    offset: int,
) -> CachedToolOutputSearchByRegexResult:
    def scan_loaded() -> CachedToolOutputSearchByRegexResult:
        compiled = regex.compile(pattern)
        page_start = offset * _MATCHES_PER_PAGE
        page_end = page_start + _MATCHES_PER_PAGE
        page_matches: list[tuple[StoredCachedToolOutput, int, int]] = []
        match_index = 0

        for stored in stored_items:
            try:
                for matched in compiled.finditer(
                    stored.text,
                    timeout=_SEARCH_TIMEOUT_SECONDS,
                ):
                    if page_start <= match_index < page_end:
                        page_matches.append((stored, matched.start(), matched.end()))
                    match_index += 1
                    if match_index >= page_end + 1:
                        break
                if match_index >= page_end + 1:
                    break
            except TimeoutError as exc:
                raise TimeoutError(
                    f"regex search exceeded {_SEARCH_TIMEOUT_SECONDS}s"
                ) from exc

        has_more = match_index > page_end
        return CachedToolOutputSearchByRegexResult(
            offset=offset,
            matched_count=len(page_matches),
            has_more=has_more,
            windows=_build_regex_windows(page_matches),
        )

    return await asyncio.to_thread(scan_loaded)


def _build_regex_windows(
    matches: Sequence[tuple[StoredCachedToolOutput, int, int]],
) -> list[CachedToolOutputRegexWindow]:
    """先分别扩展每个命中，再且仅在扩展区间相交时合并窗口。"""
    windows: list[CachedToolOutputRegexWindow] = []
    active: CachedToolOutputRegexWindow | None = None

    for stored, match_start, match_end in matches:
        start, end = _regex_window_range(
            stored.text,
            match_start=match_start,
            match_end=match_end,
        )
        highlight = CachedToolOutputRegexHighlight(
            text=stored.text[match_start:match_end],
            start_offset=match_start - start,
            end_offset=match_end - start,
        )
        if (
            active is not None
            and active.content_id == stored.content_id
            and start < active.end_offset
        ):
            old_start = active.start_offset
            active.end_offset = max(active.end_offset, end)
            active.text = stored.text[old_start:active.end_offset]
            active.highlights.append(
                CachedToolOutputRegexHighlight(
                    text=highlight.text,
                    start_offset=match_start - old_start,
                    end_offset=match_end - old_start,
                )
            )
            continue

        active = CachedToolOutputRegexWindow(
            content_id=stored.content_id,
            text=stored.text[start:end],
            start_offset=start,
            end_offset=end,
            highlights=[highlight],
        )
        windows.append(active)
    return windows


def _regex_window_range(
    text: str,
    *,
    match_start: int,
    match_end: int,
) -> tuple[int, int]:
    """每侧最多扩展 200 字符，优先包含范围内最近的句子边界。"""
    candidate_start = max(match_start - _REGEX_CONTEXT_CHARS, 0)
    candidate_end = min(match_end + _REGEX_CONTEXT_CHARS, len(text))
    left_boundary = max(
        (
            index + 1
            for index in range(candidate_start, match_start)
            if text[index] in _REGEX_SENTENCE_BOUNDARIES
        ),
        default=candidate_start,
    )
    right_boundary = next(
        (
            index + 1
            for index in range(match_end, candidate_end)
            if text[index] in _REGEX_SENTENCE_BOUNDARIES
        ),
        candidate_end,
    )
    return left_boundary, right_boundary


def _policy() -> ToolPolicy:
    return ToolPolicy(
        expose_by_default=False,
        selection_mode=ToolSelectionMode.CONTEXTUAL,
        persist_output=True,
        risk_level=ToolRiskLevel.LOW,
        required_context_keys=("session_id",),
        timeout_seconds=_TIMEOUT_SECONDS,
    )
