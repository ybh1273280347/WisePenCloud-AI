from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class DocumentParseRequest:
    file_path: str | Path  # 本地待解析文件路径
    original_filename: str | None = None  # 用户上传时的原始文件名
    mime_type: str | None = None  # 上游已知 MIME，缺失时由本地探测兜底
    source_scope: str | None = None  # 来源范围：web_public / web_custom / None
    source_kind: str | None = None  # 来源类型：如 web_fetch

    @property
    def path(self) -> Path:
        return Path(self.file_path)

    @property
    def display_name(self) -> str:
        return self.original_filename or self.path.name

    @property
    def suffix(self) -> str:
        return self.path.suffix.lower()


@dataclass(frozen=True, slots=True)
class DocumentParseResult:
    markdown: str  # 最终提供给后续工具链的 Markdown
