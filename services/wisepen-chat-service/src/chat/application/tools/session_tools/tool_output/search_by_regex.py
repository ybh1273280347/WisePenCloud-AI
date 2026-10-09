from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
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
    StoredToolContent,
    get_tool_content,
)

_MAX_REGEX_CHARS = 500
_MAX_MATCHES = 100
_DEFAULT_MAX_MATCHES = 10
_REGEX_CONTEXT_CHARS = 200
_REGEX_SENTENCE_BOUNDARIES = frozenset(".。!?！？;；\n")
_SEARCH_TIMEOUT_SECONDS = 5
_TIMEOUT_SECONDS = 300.0

_PARAMETERS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "content_id": {
            "type": "string",
            "minLength": 1,
            "description": "One cached tool output content ID.",
        },
        "pattern": {
            "type": "string",
            "minLength": 1,
            "maxLength": _MAX_REGEX_CHARS,
            "description": "Python regular expression matched against the complete stored source text.",
        },
        "start_offset": {
            "type": "integer",
            "minimum": 0,
            "default": 0,
            "description": "Absolute source character offset from which to continue searching.",
        },
        "max_matches": {
            "type": "integer",
            "minimum": 1,
            "maximum": _MAX_MATCHES,
            "default": _DEFAULT_MAX_MATCHES,
            "description": "Maximum number of regex matches to consume in this call.",
        },
    },
    "required": ["content_id", "pattern"],
    "additionalProperties": False,
}


@dataclass(slots=True)
class ToolOutputRegexWindow:
    """正则命中上下文窗口；相交命中合并后只保留命中次数。"""

    text: str
    start_offset: int
    end_offset: int
    matched_count: int


@dataclass(slots=True)
class ToolOutputRegexSearchResult:
    """一次正则搜索的窗口及正文续读位置。"""

    content_id: str
    next_offset: int  # 下一次扫描的原文字符起点，不是上下文窗口的结束位置。
    has_more: bool  # 达到命中上限且仍有可扫描位置，不保证后续存在命中。
    windows: list[ToolOutputRegexWindow]


class SearchToolOutputRegexTool:
    def __init__(self) -> None:
        self._definition = ToolDefinition(
            llm_spec=ToolLLMSpec(
                name="search_tool_output_regex",
                description=(
                    "Search one complete cached source text with a Python regular expression. "
                    "Start at start_offset and continue from next_offset. Each call consumes "
                    "up to max_matches exact matches (default 10, maximum 100), without "
                    "rescanning the preceding source text. Each "
                    "match gets up to 200 characters of nearby context, expanded toward sentence "
                    "boundaries. Overlapping contexts are merged. Window start_offset and "
                    "end_offset are absolute source offsets; inspect the text to identify matches."
                    " has_more means scanning stopped at the match limit; a follow-up call may "
                    "return no matches. Reuse content_id and pattern with start_offset=next_offset."
                ),
                parameters_schema=ToolParametersSchema(_PARAMETERS_SCHEMA),
            ),
            policy=ToolPolicy(
                expose_by_default=False,
                selection_mode=ToolSelectionMode.CONTEXTUAL,
                persist_output=True,
                risk_level=ToolRiskLevel.LOW,
                required_context_keys=("session_id",),
                timeout_seconds=_TIMEOUT_SECONDS,
            ),
            ui_spec=ToolUISpec(
                display_name="正则搜索缓存的工具输出",
                description="在一份缓存工具输出中按正则查找文本并按字符偏移续读上下文。",
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
    ) -> ToolOutputRegexSearchResult:
        del config
        try:
            session_id = context["session_id"]
            content_id = kwargs["content_id"]
            stored = await get_tool_content(
                content_id=content_id,
                session_id=session_id,
            )
            if stored is None:
                raise ToolExecutionError(
                    reason="cached_tool_output_not_found",
                    retryable=False,
                )
            return await _search_by_regex(
                stored=stored,
                pattern=kwargs["pattern"],
                start_offset=kwargs["start_offset"],
                max_matches=kwargs["max_matches"],
            )
        except ToolExecutionError:
            raise
        except regex.error as exc:
            raise ToolExecutionError(
                reason="invalid_regex_pattern",
                detail_reason=str(exc),
            ) from exc
        except Exception as exc:
            raise ToolExecutionError(
                reason="search_cached_tool_output_by_regex_failed",
                detail_reason=str(exc),
                retryable=False,
            ) from exc


async def _search_by_regex(
    *,
    stored: StoredToolContent,
    pattern: str,
    start_offset: int,
    max_matches: int = _DEFAULT_MAX_MATCHES,
) -> ToolOutputRegexSearchResult:
    """从原文绝对偏移续扫；消费指定数量命中即停止，不探测余下全文。"""
    def scan_loaded() -> ToolOutputRegexSearchResult:
        compiled = regex.compile(pattern)
        matches: list[tuple[int, int]] = []
        next_offset = start_offset
        if start_offset > len(stored.text):
            return ToolOutputRegexSearchResult(
                content_id=stored.content_id,
                next_offset=start_offset,
                has_more=False,
                windows=[],
            )
        try:
            for matched in compiled.finditer(
                stored.text,
                pos=start_offset,
                timeout=_SEARCH_TIMEOUT_SECONDS,
            ):
                matches.append((matched.start(), matched.end()))
                # 零宽命中至少推进一个字符；EOF 的零宽命中推进到 len + 1，避免续扫重复。
                next_offset = max(matched.end(), matched.start() + 1)
                if len(matches) >= max_matches:
                    break
            else:
                # 迭代耗尽说明后缀已扫完，即使没有命中也应报告扫描到正文结尾。
                next_offset = max(next_offset, len(stored.text))
        except TimeoutError as exc:
            raise TimeoutError(
                f"regex search exceeded {_SEARCH_TIMEOUT_SECONDS}s"
            ) from exc

        return ToolOutputRegexSearchResult(
            content_id=stored.content_id,
            next_offset=next_offset,
            has_more=(
                len(matches) >= max_matches
                and next_offset <= len(stored.text)
            ),
            windows=_build_regex_windows(stored, matches),
        )

    return await asyncio.to_thread(scan_loaded)


def _build_regex_windows(
    stored: StoredToolContent,
    matches: Sequence[tuple[int, int]],
) -> list[ToolOutputRegexWindow]:
    """先扩展每个命中上下文，再合并相交的原文区间。"""
    windows: list[ToolOutputRegexWindow] = []
    active: ToolOutputRegexWindow | None = None

    for match_start, match_end in matches:
        start, end = _regex_window_range(
            stored.text,
            match_start=match_start,
            match_end=match_end,
        )
        if active is not None and start < active.end_offset:
            old_start = active.start_offset
            active.end_offset = max(active.end_offset, end)
            active.text = stored.text[old_start:active.end_offset]
            active.matched_count += 1
            continue

        active = ToolOutputRegexWindow(
            text=stored.text[start:end],
            start_offset=start,
            end_offset=end,
            matched_count=1,
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
