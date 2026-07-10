from __future__ import annotations

from chat.application.tools.document_tools.document_parse.core.errors import (
    UnsupportedDocumentFormatError,
)
from chat.application.tools.document_tools.document_parse.core.models import (
    DocumentParseRequest,
    DocumentParseResult,
)
from chat.application.tools.utils.file_type_detect import FileType, detect_file_type
from .fallback import FallbackConverter
from .html import HtmlConverter
from .json import JsonConverter
from .office import DocxConverter, PptxConverter
from .pdf import MinerUConverter
from .plaintext import PlaintextConverter
from .spreadsheet import SpreadsheetConverter

_SPREADSHEET_TYPES = frozenset({"csv", "tsv", "xls", "xlsx"})
_SPREADSHEET_MIME_TYPES = frozenset({
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/csv",
    "text/tab-separated-values",
})

_HTML_TYPES = frozenset({"html", "htm"})
_HTML_MIME_TYPES = frozenset({"text/html", "application/xhtml+xml"})

_JSON_TYPES = frozenset({"json", "jsonl", "ndjson"})
_JSON_MIME_TYPES = frozenset({"application/json", "application/x-ndjson"})

_PLAINTEXT_EXTENSIONS = frozenset({
    "txt", "text", "md", "markdown", "rst", "log",
    "py", "java", "kt", "kts", "c", "h", "cpp", "hpp", "cs",
    "go", "rs", "js", "jsx", "ts", "tsx", "vue", "svelte",
    "sh", "bash", "zsh", "ps1", "sql", "xml", "yaml", "yml",
    "toml", "ini", "cfg", "conf", "properties", "env",
})

_BLOCKED_EXTENSIONS = frozenset({
    "7z", "a", "apk", "avi", "bz2", "db", "dll", "dmg", "exe", "flac",
    "gz", "ico", "iso", "jar", "jpeg", "jpg", "m4a", "mkv", "mov", "mp3",
    "mp4", "otf", "png", "rar", "so", "sqlite", "tar", "ttf", "wav", "webm",
    "webp", "woff", "woff2", "zip",
})
_BLOCKED_LABELS = frozenset({
    "7zip", "apk", "archive", "avi", "bmp", "database", "dll", "dmg", "elf",
    "exe", "flac", "font", "gif", "gzip", "iso", "jpeg", "macho", "mp3", "mp4",
    "ogg", "pebin", "png", "rar", "sqlite", "tar", "tiff", "wav", "webm",
    "webp", "zip",
})
_BLOCKED_MIME_PREFIXES = ("audio/", "font/", "image/", "video/")
_BLOCKED_MIME_TYPES = frozenset({
    "application/java-archive",
    "application/vnd.android.package-archive",
    "application/x-7z-compressed",
    "application/x-dosexec",
    "application/x-executable",
    "application/x-rar-compressed",
    "application/x-sharedlib",
    "application/x-sqlite3",
    "application/zip",
})

# Office Open XML、EPUB、ODT 本质上是 ZIP 容器，不能仅因嗅探结果为 zip 就拦截。
_ZIP_DOCUMENT_EXTENSIONS = frozenset({"docx", "epub", "odt", "pptx", "xlsx"})


class DocumentConverterRouter:
    __slots__ = (
        "_mineru_converter",
        "_docx_converter",
        "_pptx_converter",
        "_spreadsheet_converter",
        "_html_converter",
        "_json_converter",
        "_plaintext_converter",
        "_fallback_converter",
    )

    def __init__(
            self,
            *,
            mineru_converter: MinerUConverter,
            docx_converter: DocxConverter | None = None,
            pptx_converter: PptxConverter | None = None,
            spreadsheet_converter: SpreadsheetConverter | None = None,
            html_converter: HtmlConverter | None = None,
            json_converter: JsonConverter | None = None,
            plaintext_converter: PlaintextConverter | None = None,
            fallback_converter: FallbackConverter | None = None,
    ) -> None:
        self._mineru_converter = mineru_converter
        self._docx_converter = docx_converter or DocxConverter()
        self._pptx_converter = pptx_converter or PptxConverter()
        self._spreadsheet_converter = spreadsheet_converter or SpreadsheetConverter()
        self._html_converter = html_converter or HtmlConverter()
        self._json_converter = json_converter or JsonConverter()
        self._plaintext_converter = plaintext_converter or PlaintextConverter()
        self._fallback_converter = fallback_converter or FallbackConverter()

    async def convert(
            self,
            request: DocumentParseRequest,
    ) -> DocumentParseResult:
        file_name = request.display_name
        detected = detect_file_type(
            request.file_path,
            fallback_name=file_name,
        )
        detected = FileType(
            extension=detected.extension,
            label=detected.label,
            mime_type=(
                request.mime_type
                or detected.mime_type
                or ""
            ).partition(";")[0].strip().lower(),
        )

        # 明确的二进制、媒体、压缩包等格式不进入通用 fallback。
        if _is_blocked_format(detected):
            raise UnsupportedDocumentFormatError(
                file_name=file_name,
                extension=detected.extension,
                mime_type=detected.mime_type,
            )

        converter = self._select_converter(detected) or self._fallback_converter
        return await converter.convert(
            request.file_path,
            file_name=file_name,
            mime_type=detected.mime_type or None,
        )

    def _select_converter(self, detected: FileType):
        extension = detected.extension
        label = detected.label
        mime_type = detected.mime_type

        if extension == "pdf" or label == "pdf" or mime_type == "application/pdf":
            return self._mineru_converter

        if (
                extension == "docx"
                or label == "docx"
                or "wordprocessingml" in mime_type
        ):
            return self._docx_converter

        if (
                extension == "pptx"
                or label == "pptx"
                or "presentationml" in mime_type
        ):
            return self._pptx_converter

        if (
                extension in _SPREADSHEET_TYPES
                or label in _SPREADSHEET_TYPES
                or mime_type in _SPREADSHEET_MIME_TYPES
        ):
            return self._spreadsheet_converter

        if (
                extension in _HTML_TYPES
                or label in _HTML_TYPES
                or mime_type in _HTML_MIME_TYPES
        ):
            return self._html_converter

        if (
                extension in _JSON_TYPES
                or label in _JSON_TYPES
                or mime_type in _JSON_MIME_TYPES
        ):
            return self._json_converter

        # 代码、配置、Markdown 等文本格式统一走最轻量的直接解码链路。
        if extension in _PLAINTEXT_EXTENSIONS or mime_type.startswith("text/"):
            return self._plaintext_converter

        return None
def _is_blocked_format(detected: FileType) -> bool:
    # DOCX/PPTX/XLSX 等容器格式被识别成 ZIP 时仍应继续路由。
    if (
            detected.extension in _ZIP_DOCUMENT_EXTENSIONS
            and (
                detected.label == "zip"
                or detected.mime_type == "application/zip"
            )
    ):
        return False

    return (
        detected.extension in _BLOCKED_EXTENSIONS
        or detected.label in _BLOCKED_LABELS
        or detected.mime_type in _BLOCKED_MIME_TYPES
        or detected.mime_type.startswith(_BLOCKED_MIME_PREFIXES)
    )
