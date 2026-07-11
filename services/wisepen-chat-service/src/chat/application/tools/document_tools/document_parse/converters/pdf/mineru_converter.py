from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import anyio
import httpx

from chat.application.tools.document_tools.document_parse.core.errors import (
    DocumentTooLargeError,
    RemoteParserError,
    RemoteParserTimeoutError,
)
from chat.application.tools.document_tools.document_parse.core.models import (
    DocumentParseResult,
)
from .result_archive import extract_mineru_markdown

_STREAM_CHUNK_SIZE = 1024 * 1024
_ERROR_PREVIEW_BYTES = 4096

# MinerU 自部署解析参数统一放在这里，后续可整体迁移至 Nacos。
_MINERU_PARSE_FORM: dict[str, str] = {
    "backend": "pipeline",
    "lang_list": "ch",
    "parse_method": "auto",
    "formula_enable": "true",
    "table_enable": "true",
    "return_md": "true",
    "return_content_list": "true",
    "return_middle_json": "false",
    "return_model_output": "false",
    "return_images": "false",
    "response_format_zip": "true",
    "return_original_file": "false",
    "client_side_output_generation": "false",
    "start_page_id": "0",
    "end_page_id": "99999",
}


class MinerUConverter:
    __slots__ = (
        "_http_client",
        "_api_url",
        "_connect_timeout_seconds",
        "_write_timeout_seconds",
        "_read_timeout_seconds",
        "_pool_timeout_seconds",
        "_max_response_bytes",
    )

    def __init__(
            self,
            *,
            http_client: httpx.AsyncClient,
            api_url: str,
            connect_timeout_seconds: float = 20.0,
            write_timeout_seconds: float = 1800.0,
            read_timeout_seconds: float = 3600.0,
            pool_timeout_seconds: float = 20.0,
            max_response_bytes: int = 104_857_600,
    ) -> None:
        api_url = api_url.strip()
        if not api_url:
            raise ValueError("MinerU API URL must not be empty.")

        self._http_client = http_client
        self._api_url = api_url
        self._connect_timeout_seconds = max(
            0.1,
            float(connect_timeout_seconds),
        )
        self._write_timeout_seconds = max(
            0.1,
            float(write_timeout_seconds),
        )
        self._read_timeout_seconds = max(
            0.1,
            float(read_timeout_seconds),
        )
        self._pool_timeout_seconds = max(
            0.1,
            float(pool_timeout_seconds),
        )
        self._max_response_bytes = max(
            1,
            int(max_response_bytes),
        )

    async def convert(
            self,
            file_path: Path,
            *,
            file_name: str,
            mime_type: str | None = None,
    ) -> DocumentParseResult:
        if not file_path.is_file():
            raise FileNotFoundError(file_path)

        upload_file_name = (
            file_name
            if file_name.lower().endswith(".pdf")
            else f"{file_name}.pdf"
        )

        with tempfile.TemporaryDirectory(
                prefix="mineru_result_",
        ) as temp_dir:
            zip_path = Path(temp_dir) / "result.zip"

            await self._request_parse(
                file_path=file_path,
                upload_file_name=upload_file_name,
                mime_type=mime_type or "application/pdf",
                zip_path=zip_path,
            )

            markdown = await asyncio.to_thread(
                extract_mineru_markdown,
                zip_path,
                file_name=file_name,
                max_output_bytes=self._max_response_bytes,
            )

        return DocumentParseResult(markdown=markdown)

    async def _request_parse(
            self,
            *,
            file_path: Path,
            upload_file_name: str,
            mime_type: str,
            zip_path: Path,
    ) -> None:
        timeout = httpx.Timeout(
            connect=self._connect_timeout_seconds,
            write=self._write_timeout_seconds,
            read=self._read_timeout_seconds,
            pool=self._pool_timeout_seconds,
        )

        try:
            with file_path.open("rb") as source:
                async with self._http_client.stream(
                        "POST",
                        self._api_url,
                        headers={"Accept": "application/zip"},
                        data=_MINERU_PARSE_FORM,
                        files={
                            "files": (
                                upload_file_name,
                                source,
                                mime_type,
                            )
                        },
                        timeout=timeout,
                ) as response:
                    if response.is_error:
                        detail = await _response_preview(response)
                        raise RemoteParserError(
                            "MinerU parsing failed with HTTP "
                            f"{response.status_code}: "
                            f"{detail or 'no error detail'}."
                        )

                    await self._write_zip_response(
                        response,
                        zip_path=zip_path,
                    )

        except (RemoteParserError, DocumentTooLargeError):
            raise
        except httpx.TimeoutException as exc:
            raise RemoteParserTimeoutError(
                "MinerU parsing request timed out."
            ) from exc
        except httpx.HTTPError as exc:
            raise RemoteParserError(
                f"MinerU parsing request failed: {exc}."
            ) from exc

    async def _write_zip_response(
            self,
            response: httpx.Response,
            *,
            zip_path: Path,
    ) -> None:
        content_length = response.headers.get("content-length")
        if content_length:
            try:
                declared_size = int(content_length)
            except ValueError as exc:
                raise RemoteParserError(
                    "MinerU returned an invalid content length."
                ) from exc

            if declared_size < 0:
                raise RemoteParserError(
                    "MinerU returned a negative content length."
                )

            if declared_size > self._max_response_bytes:
                raise DocumentTooLargeError(
                    "MinerU result exceeds "
                    f"{self._max_response_bytes} bytes."
                )

        written = 0
        signature = bytearray()

        async with await anyio.open_file(zip_path, "wb") as output:
            async for chunk in response.aiter_bytes(
                    chunk_size=_STREAM_CHUNK_SIZE,
            ):
                if len(signature) < 2:
                    signature.extend(
                        chunk[:2 - len(signature)]
                    )

                written += len(chunk)
                if written > self._max_response_bytes:
                    raise DocumentTooLargeError(
                        "MinerU result exceeds "
                        f"{self._max_response_bytes} bytes."
                    )

                await output.write(chunk)

        content_type = response.headers.get(
            "content-type",
            "",
        ).lower()

        if (
                written == 0
                or (
                    "zip" not in content_type
                    and bytes(signature) != b"PK"
                )
        ):
            raise RemoteParserError(
                "MinerU did not return a ZIP result."
            )


async def _response_preview(
        response: httpx.Response,
) -> str:
    preview = bytearray()

    async for chunk in response.aiter_bytes():
        preview.extend(
            chunk[:_ERROR_PREVIEW_BYTES - len(preview)]
        )

        if len(preview) >= _ERROR_PREVIEW_BYTES:
            break

    return preview.decode(
        "utf-8",
        errors="replace",
    ).strip()