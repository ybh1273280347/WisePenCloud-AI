from __future__ import annotations

import re
from collections.abc import Iterable

from markdown_it import MarkdownIt
from markdown_it.token import Token

from chat.application.tools.common.tool_content_store.core.models import StoredToolContent
from chat.application.tools.session_tools.tool_content_read.chunk_selector import select_chunks
from chat.application.tools.session_tools.tool_content_read.content_loader import ToolContentLoader
from chat.application.tools.session_tools.tool_content_read.content_window_builder import (
    ToolContentWindowBuilder,
)
from chat.application.tools.session_tools.tool_content_read.models import (
    ToolContentReadMatch,
    ToolContentReadResult,
    ToolContentRegexReadRequest,
)

_MARKDOWN = MarkdownIt("commonmark")
_WORD_MARKER_RE = re.compile(r"(?<=\w)[*_]+(?=\w)")
_TEXT_TOKEN_TYPES = {"text", "code_inline", "code_block", "fence"}
_BREAK_TOKEN_TYPES = {"softbreak", "hardbreak"}


class ToolContentInvalidRegexError(ValueError):
    """正则表达式语法无效。"""


class RegexMatchReader:
    """跨文档正则 reader：按 chunk 扫描，命中后构造扩展窗口。"""

    __slots__ = ("_loader", "_window_builder")

    def __init__(
            self,
            *,
            loader: ToolContentLoader,
            window_builder: ToolContentWindowBuilder,
    ) -> None:
        self._loader = loader
        self._window_builder = window_builder

    async def read(
            self,
            *,
            request: ToolContentRegexReadRequest,
            session_id: str,
    ) -> ToolContentReadResult:
        stored_items, failed = await self._loader.load_many(
            content_ids=request.content_ids,
            session_id=session_id,
        )
        return ToolContentReadResult(
            matches=self._read_loaded(stored_items, request),
            failed=failed,
        )

    def _read_loaded(
            self,
            stored_items: tuple[tuple[str, StoredToolContent], ...],
            request: ToolContentRegexReadRequest,
    ) -> tuple[ToolContentReadMatch, ...]:
        try:
            regex = re.compile(request.pattern)
            markdown_regex = _compile_markdown_regex(regex)
        except re.error as exc:
            raise ToolContentInvalidRegexError(str(exc)) from exc

        max_matches = max(request.max_matches, 0)
        if max_matches == 0:
            return ()

        matches: list[ToolContentReadMatch] = []

        for content_id, stored in stored_items:
            chunks = select_chunks(stored, request.selector)

            for chunk in chunks:
                text = ToolContentWindowBuilder.chunk_text(stored, chunk)
                if not _matches(regex, markdown_regex, text):
                    continue

                matches.append(
                    ToolContentReadMatch(
                        content_id=content_id,
                        window=self._window_builder.expand(
                            stored,
                            chunks=chunks,
                            center_chunk=chunk.chunk_index,
                            merge_before=request.merge_before,
                            merge_after=request.merge_after,
                        ),
                    )
                )

                if len(matches) >= max_matches:
                    return tuple(matches)

        return tuple(matches)


def _matches(
        regex: re.Pattern[str],
        markdown_regex: re.Pattern[str] | None,
        text: str,
) -> bool:
    """在原始 Markdown 及其等价文本视图上执行匹配。"""
    if regex.search(text):
        return True

    variants = tuple(
        dict.fromkeys(
            candidate
            for candidate in (
                _markdown_plain_text(text),
                _WORD_MARKER_RE.sub("", text),
            )
            if candidate and candidate != text
        )
    )

    if any(regex.search(candidate) for candidate in variants):
        return True

    return markdown_regex is not None and any(
        markdown_regex.search(candidate)
        for candidate in variants
    )


def _compile_markdown_regex(
        regex: re.Pattern[str],
) -> re.Pattern[str] | None:
    """放宽正则源码中的字面量下划线，兼容 Markdown 强调边界。"""
    pattern = _relax_literal_underscores(regex.pattern)
    return re.compile(pattern, regex.flags) if pattern != regex.pattern else None


def _markdown_plain_text(text: str) -> str:
    """从 Markdown token 中提取近似渲染文本。"""
    try:
        tokens = _MARKDOWN.parse(text)
    except Exception:
        return text

    parts: list[str] = []
    for token in _flatten_tokens(tokens):
        if token.type in _TEXT_TOKEN_TYPES:
            parts.append(token.content)
        elif token.type in _BREAK_TOKEN_TYPES:
            parts.append("\n")

    return "".join(parts)


def _flatten_tokens(tokens: Iterable[Token]) -> Iterable[Token]:
    for token in tokens:
        yield token
        if token.children:
            yield from _flatten_tokens(token.children)


def _relax_literal_underscores(pattern: str) -> str:
    """将字符类之外的字面量下划线改写为下划线或空白序列。"""
    parts: list[str] = []
    escaped = False
    in_class = False

    for char in pattern:
        if escaped:
            parts.append(char)
            escaped = False
        elif char == "\\":
            parts.append(char)
            escaped = True
        elif char == "[":
            parts.append(char)
            in_class = True
        elif char == "]" and in_class:
            parts.append(char)
            in_class = False
        else:
            parts.append(r"[_\s]+" if char == "_" and not in_class else char)

    return "".join(parts)