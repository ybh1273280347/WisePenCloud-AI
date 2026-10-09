from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from common.utils.markdown import Section

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
from chat.core.config.app_settings import settings

_TIMEOUT_SECONDS = 300.0
_PARAMETERS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "content_id": {"type": "string", "minLength": 1},
        "section_id": {
            "type": "string",
            "minLength": 1,
            "description": "Exact section ID from the cached structure outline.",
        },
        "scope": {
            "type": "string",
            "enum": ["own", "subtree"],
            "default": "own",
            "description": "Read this section's own span or its complete subtree span.",
        },
        "offset": {
            "type": "integer",
            "minimum": 0,
            "default": 0,
            "description": "Zero-based page number.",
        },
    },
    "required": ["content_id", "section_id"],
    "additionalProperties": False,
}


@dataclass(slots=True)
class CachedToolOutputReadBySectionResult:
    """一个 Section 原文页；source offsets 是原文字符半开区间。"""

    content_id: str
    section_id: str
    title: str
    section_path: str
    scope: str
    offset: int
    text: str
    start_offset: int
    end_offset: int
    has_more: bool
    reason: str | None = None


class CachedToolOutputReadBySectionTool:
    def __init__(self) -> None:
        self._definition = ToolDefinition(
            llm_spec=ToolLLMSpec(
                name="read_cached_tool_output_by_section",
                description=(
                    "Read one cached section from its original source span. "
                    "scope=own reads through the next heading at the same or "
                    "higher tree level; scope=subtree includes all descendants. "
                    "Long sections use zero-based page numbers in offset. "
                    "Continue with offset + 1 while has_more is true."
                ),
                parameters_schema=ToolParametersSchema(_PARAMETERS_SCHEMA),
            ),
            policy=_policy(),
            ui_spec=ToolUISpec(
                display_name="按章节读取缓存的工具输出",
                description="按原始章节范围分页读取一个章节。",
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
    ) -> CachedToolOutputReadBySectionResult:
        del config
        try:
            content_id = kwargs["content_id"]
            section_id = kwargs["section_id"]
            scope = kwargs.get("scope", "own")
            offset = kwargs.get("offset", 0)
            if scope not in ("own", "subtree"):
                raise ValueError("scope must be 'own' or 'subtree'")
            if offset < 0:
                raise ValueError("offset must be a non-negative page number")

            stored = await get_tool_content(
                content_id=content_id,
                session_id=context["session_id"],
            )
            if stored is None:
                return _missing_result(content_id, section_id, scope, offset)
            return _read_by_section(
                content_id=content_id,
                section_id=section_id,
                scope=scope,
                offset=offset,
                sections=stored.sections,
                stored=stored,
                char_budget=settings.TOOL_CONTENT_READ_WINDOW_CHAR_BUDGET,
            )
        except Exception as exc:
            raise ToolExecutionError(
                reason="read_cached_tool_output_by_section_failed",
                detail_reason=str(exc),
                retryable=False,
            ) from exc


def _read_by_section(
    *,
    content_id: str,
    section_id: str,
    scope: Literal["own", "subtree"],
    offset: int,
    sections: tuple[Section, ...] | list[Section],
    stored: StoredCachedToolOutput,
    char_budget: int,
) -> CachedToolOutputReadBySectionResult:
    section = next(
        (item for item in sections if item.section_id == section_id),
        None,
    )
    if section is None:
        return _missing_result(content_id, section_id, scope, offset)

    span = section.own_span if scope == "own" else section.subtree_span
    page_start = min(span.start_offset + offset * char_budget, span.end_offset)
    page_end = min(page_start + char_budget, span.end_offset)
    return CachedToolOutputReadBySectionResult(
        content_id=content_id,
        section_id=section.section_id,
        title=section.title,
        section_path=" > ".join(section.section_path),
        scope=scope,
        offset=offset,
        text=stored.text[page_start:page_end],
        start_offset=page_start,
        end_offset=page_end,
        has_more=page_end < span.end_offset,
    )


def _missing_result(
    content_id: str,
    section_id: str,
    scope: str,
    offset: int,
) -> CachedToolOutputReadBySectionResult:
    return CachedToolOutputReadBySectionResult(
        content_id=content_id,
        section_id=section_id,
        title="",
        section_path="",
        scope=scope,
        offset=offset,
        text="",
        start_offset=0,
        end_offset=0,
        has_more=False,
        reason="section_not_found",
    )


def _policy() -> ToolPolicy:
    return ToolPolicy(
        expose_by_default=False,
        selection_mode=ToolSelectionMode.CONTEXTUAL,
        persist_output=True,
        risk_level=ToolRiskLevel.LOW,
        required_context_keys=("session_id",),
        timeout_seconds=_TIMEOUT_SECONDS,
    )
