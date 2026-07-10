from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class DocumentParseRequest:
    file_path: Path  # 本地待解析文件路径
    original_filename: str | None = None  # 用户上传时的原始文件名
    mime_type: str | None = None  # 上游已知 MIME，缺失时由本地探测兜底

    @property
    def display_name(self) -> str:
        return self.original_filename or self.file_path.name


@dataclass(frozen=True, slots=True)
class DocumentParseResult:
    markdown: str  # 最终提供给后续工具链的 Markdown
