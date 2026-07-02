from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OcrPageResult:
    page_number: int  # 从 1 开始的页码
    markdown: str  # OCR 产出的页面 Markdown

    @property
    def page_marker(self) -> str:
        return f"<!-- page {self.page_number} -->"

    def markdown_with_page_marker(self) -> str:
        body = self.markdown.strip()
        return self.page_marker if not body else f"{self.page_marker}\n\n{body}"
