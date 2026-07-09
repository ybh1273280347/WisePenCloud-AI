from __future__ import annotations

import re

import trafilatura

from common.logger import warn
from .base import CleanedOutput
from .html_prune_policy import build_prune_xpath


class TrafilaturaCleaner:
    """web_fetch 专用 trafilatura 网页正文清洗器。"""

    __slots__ = ("_enable_dom_prune",)

    def __init__(self, *, enable_dom_prune: bool = True) -> None:
        self._enable_dom_prune = enable_dom_prune

    @property
    def name(self) -> str:
        return "trafilatura"

    def clean(self, raw_html: str, *, url: str | None = None) -> CleanedOutput:
        if not raw_html or not raw_html.strip():
            return CleanedOutput(markdown=None, cleaner=self.name)

        try:
            markdown = trafilatura.extract(
                raw_html.strip(),
                url=url,
                output_format="markdown",
                include_comments=False,
                include_tables=True,
                include_links=True,
                favor_precision=False,
                favor_recall=True,
                prune_xpath=build_prune_xpath(url) if self._enable_dom_prune else None,
            )
        except Exception as exc:  # noqa: BLE001 - trafilatura 异常统一降级为空结果
            warn("web_fetch trafilatura clean failed", url=url, error=str(exc))
            return CleanedOutput(markdown=None, cleaner=self.name)

        return CleanedOutput(
            markdown=_normalize_markdown(markdown),
            cleaner=self.name,
            title=None,
        )


def _normalize_markdown(markdown: str | None) -> str | None:
    if not markdown:
        return None

    text = "\n".join(markdown.splitlines()).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text or None
