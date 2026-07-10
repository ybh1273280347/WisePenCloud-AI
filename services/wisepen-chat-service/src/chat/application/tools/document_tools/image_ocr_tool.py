from __future__ import annotations

import contextlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from chat.application.tools.common.tool_run_file_store import ToolRunFileStore
from chat.application.tools.common.tool_run_file_store.core.errors import tool_file_error_reason
from chat.application.tools.core import (
    ToolDefinition,
    ToolExecutionError,
    ToolLLMSpec,
    ToolParametersSchema,
    ToolPolicy,
    ToolRiskLevel,
)
from chat.application.tools.core.tool_return import ToolReturn
from chat.application.tools.document_tools.ocr import OcrPageResult
from chat.application.tools.utils.file_type_detect import detect_mime_type
from chat.application.tools.utils.url import (
    DownloadedUrl,
    UrlDownloadError,
    UrlDownloadUnsupportedUrlError,
    UrlSecurityError,
    download_url,
    filename_from_url,
    validate_public_http_url,
)

IMAGE_OCR_TOOL_TIMEOUT_SECONDS = 300.0
IMAGE_OCR_MAX_DOWNLOAD_BYTES = 52_428_800


@dataclass(frozen=True, slots=True)
class ImageOcrToolResult:
    status: str
    markdown: str | None = None
    file_name: str | None = None
    reason: str | None = None


class ImageOcrTool:
    """按需从图片中提取文字。"""

    __slots__ = (
        "_definition",
        "_file_store",
        "_max_download_bytes",
        "_ocr_client",
        "_url_download_http_client",
    )

    def __init__(
            self,
            *,
            file_store: ToolRunFileStore,
            ocr_client: Any | None = None,
            url_download_http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._file_store = file_store
        self._ocr_client = ocr_client
        self._url_download_http_client = url_download_http_client
        self._max_download_bytes = IMAGE_OCR_MAX_DOWNLOAD_BYTES
        self._definition = ToolDefinition(
            llm_spec=ToolLLMSpec(
                name="image_ocr",
                description=(
                    "Extract text from an image only when visual inspection is not enough.\n"
                    "\n"
                    "WHEN TO TRIGGER:\n"
                    "  - Trigger after you already have an image source and need precise text from the image.\n"
                    "  - Use file_ref for internal tfile_* references returned by previous tools.\n"
                    "  - Use file_path for a direct user-provided image URL/path.\n"
                    "DO NOT TRIGGER when:\n"
                    "  - You can answer from normal multimodal image understanding without extra OCR.\n"
                    "  - You need to parse PDF, Office, or spreadsheet documents; use document_parse instead.\n"
                    "  - You need specialized table/chart understanding beyond text extraction.\n"
                    "\n"
                    "INPUT RULES:\n"
                    "  - Provide exactly one of file_ref or file_path.\n"
                    "  - Do not invent local paths. file_path must come from the user or a trusted upstream tool.\n"
                    "\n"
                    "OUTPUT RULES:\n"
                    "  - Successful OCR text is returned as Markdown content.\n"
                    "  - If no text is found, the result is successful with no cached content."
                ),
                parameters_schema=ToolParametersSchema(
                    {
                        "type": "object",
                        "properties": {
                            "file_ref": {
                                "type": "string",
                                "minLength": 1,
                                "description": "Internal tfile_* image reference from a previous tool.",
                            },
                            "file_path": {
                                "type": "string",
                                "minLength": 1,
                                "description": "Direct user-provided image URL/path or trusted upstream file path.",
                            },
                        },
                        "additionalProperties": False,
                    }
                ),
            ),
            policy=ToolPolicy(
                expose_by_default=True,
                persist_output=True,
                risk_level=ToolRiskLevel.LOW,
                required_context_keys=("user_id", "session_id"),
                timeout_seconds=IMAGE_OCR_TOOL_TIMEOUT_SECONDS,
                cache_chunked=True,
            ),
        )

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    async def execute(self, context: dict[str, Any], **kwargs: Any) -> ToolReturn:
        if self._ocr_client is None:
            raise ToolExecutionError(
                reason="image_ocr_unavailable",
                detail_reason="Image OCR requires an OCR client.",
                retryable=False,
            )

        file_ref = str(kwargs.get("file_ref") or "").strip()
        file_path = str(kwargs.get("file_path") or "").strip()

        if bool(file_ref) == bool(file_path):
            raise ToolExecutionError(
                reason="invalid_image_ocr_input",
                detail_reason="Provide exactly one of file_ref or file_path.",
                retryable=False,
            )

        if file_ref:
            result = await self._parse_file_ref(
                user_id=str(context["user_id"]),
                session_id=str(context["session_id"]),
                file_ref=file_ref,
            )
        else:
            result = await self._parse_file_path(file_path)

        cacheable_texts: tuple[str, ...] = ()
        if result.markdown:
            cacheable_texts = (result.markdown,)

        return ToolReturn(
            tag="image_ocr_result",
            visible_result={
                "status": result.status,
                "file_name": result.file_name,
                "reason": result.reason,
            },
            cacheable_texts=cacheable_texts,
        )

    async def _parse_file_ref(
            self,
            *,
            user_id: str,
            session_id: str,
            file_ref: str,
    ) -> ImageOcrToolResult:
        try:
            resolved = await self._file_store.resolve_ref(
                user_id=user_id,
                session_id=session_id,
                ref_id=file_ref,
            )
        except Exception as e:
            return ImageOcrToolResult(status="failed", reason=tool_file_error_reason(e))

        return await self._parse_image_path(
            path=Path(resolved.path),
            file_name=resolved.filename,
            content_type=resolved.content_type,
        )

    async def _parse_file_path(self, file_path: str) -> ImageOcrToolResult:
        if file_path.startswith(("http://", "https://")):
            return await self._parse_image_url(file_path)
        return await self._parse_image_path(
            path=Path(file_path),
            file_name=Path(file_path).name,
            content_type=None,
        )

    async def _parse_image_url(self, url: str) -> ImageOcrToolResult:
        if self._url_download_http_client is None:
            return ImageOcrToolResult(status="failed", reason="image_url_fetch_unavailable")

        raw: DownloadedUrl | None = None
        try:
            url = validate_public_http_url(url)
            raw = await download_url(
                url,
                http_client=self._url_download_http_client,
                max_response_bytes=self._max_download_bytes,
            )
            return await self._parse_image_path(
                path=Path(raw.file_path),
                file_name=filename_from_url(raw.source_url),
                content_type=raw.content_type,
            )
        except UrlDownloadUnsupportedUrlError as e:
            reason = (
                "image_url_not_file"
                if e.reason == "url_resolved_to_html"
                else f"image_url_fetch_failed:{e.reason}"
            )
            return ImageOcrToolResult(status="failed", reason=reason)
        except UrlSecurityError as e:
            return ImageOcrToolResult(
                status="failed",
                reason=f"invalid_image_url:{e}",
            )
        except UrlDownloadError as e:
            return ImageOcrToolResult(
                status="failed",
                reason=f"image_url_fetch_failed:{e.reason}",
            )
        finally:
            if raw is not None and raw.file_path is not None:
                with contextlib.suppress(OSError):
                    Path(raw.file_path).unlink(missing_ok=True)

    async def _parse_image_path(
            self,
            *,
            path: Path,
            file_name: str | None,
            content_type: str | None,
    ) -> ImageOcrToolResult:
        if not path.is_file():
            return ImageOcrToolResult(
                status="failed",
                file_name=file_name,
                reason="file_path_unavailable",
            )

        if not _is_image(path=path, content_type=content_type):
            return ImageOcrToolResult(status="failed", file_name=file_name, reason="not_image")

        try:
            page: OcrPageResult = await self._ocr_client.parse_image(file_path=path)
        except Exception:
            return ImageOcrToolResult(status="failed", file_name=file_name, reason="ocr_failed")

        markdown = page.markdown_with_page_marker().strip()
        return ImageOcrToolResult(
            status="success",
            markdown=markdown or None,
            file_name=file_name,
        )


def _is_image(*, path: Path, content_type: str | None) -> bool:
    mime_type = (content_type or detect_mime_type(path)).split(";", maxsplit=1)[0].strip().lower()
    return mime_type.startswith("image/")
