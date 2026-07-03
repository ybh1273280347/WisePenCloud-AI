from __future__ import annotations

import re

from bs4 import BeautifulSoup
from markdownify import ATX, markdownify as markdownify_html


class HtmlToMarkdownRenderer:
    """确定性 HTML 片段 Markdown 渲染器。"""

    def __init__(self, *, remove_noise_tags: bool = True) -> None:
        self._remove_noise_tags = remove_noise_tags

    def render(self, html: str) -> str | None:
        stripped = html.strip()
        if not stripped:
            return None

        try:
            cleaned_html = (
                self._remove_noise_tags_from_html(stripped)
                if self._remove_noise_tags
                else stripped
            )
            rendered = markdownify_html(
                cleaned_html,
                heading_style=ATX,
                bullets="-",
                autolinks=False,
                default_title=False,
                table_infer_header=True,
                escape_asterisks=False,
                escape_underscores=False,
            )
        except Exception:
            return None

        return normalize_markdown(rendered)

    @staticmethod
    def _remove_noise_tags_from_html(html: str) -> str:
        """从 HTML 片段中剔除不适合进入大模型或知识库的噪声标签。"""
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.select("script, style, noscript, template, svg, canvas"):
            tag.decompose()
        return str(soup)


def normalize_markdown(markdown: str | None) -> str | None:
    """规范化换行符，并压缩多余的连续空行。"""
    if not markdown:
        return None

    text = "\n".join(markdown.splitlines()).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text or None
