from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from itertools import batched
from pathlib import Path
from typing import Any

import httpx

from chat.application.tools.common.file_reference_store import FileReferenceStore
from chat.application.tools.common.file_reference_store.core.errors import (
    file_reference_error_reason,
)
from chat.application.tools.common.web_content_cache import (
    WebContentCacheRepository,
)
from chat.application.tools.core import (
    ToolDefinition,
    ToolExecutionError,
    ToolLLMSpec,
    ToolParametersSchema,
    ToolPolicy,
    ToolRiskLevel,
)
from chat.application.tools.core.tool_return import ToolReturn
from chat.application.tools.document_tools.document_parse.cache import (
    DocumentParseCache,
)
from chat.application.tools.document_tools.document_parse.core.errors import (
    DocumentDecodeError,
    DocumentParseError,
    DocumentTooLargeError,
    RemoteParserError,
    RemoteParserTimeoutError,
    UnsupportedDocumentFormatError,
)
from chat.application.tools.document_tools.document_parse.core.models import (
    DocumentParseRequest,
)
from chat.application.tools.document_tools.document_parse.service import (
    DocumentParseService,
)
from chat.application.tools.utils.url import (
    DownloadedUrl,
    UrlDownloadError,
    UrlDownloadUnsupportedUrlError,
    UrlSecurityError,
    download_url,
    filename_from_url,
    validate_public_http_url,
)

DOCUMENT_PARSE_TOOL_TIMEOUT_SECONDS = 660.0
DOCUMENT_PARSE_CONCURRENCY = 8
DOCUMENT_PARSE_MAX_DOWNLOAD_BYTES = 52_428_800


@dataclass(frozen=True, slots=True)
class DocumentParseToolItem:
    source: str
    status: str
    file_name: str | None = None
    reason: str | None = None


class DocumentParseTool:
    """批量解析统一文件引用或明显文档直链。"""

    __slots__ = (
        "_cache",
        "_definition",
        "_file_store",
        "_parse_service",
        "_url_download_http_client",
    )

    def __init__(
            self,
            *,
            file_store: FileReferenceStore,
            parse_service: DocumentParseService,
            content_cache_repository: WebContentCacheRepository | None = None,
            url_download_http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._file_store = file_store
        self._parse_service = parse_service
        self._cache = DocumentParseCache(
            content_cache_repository=content_cache_repository
        )
        self._url_download_http_client = url_download_http_client
        self._definition = ToolDefinition(
            llm_spec=ToolLLMSpec(
                name="document_parse",
                description=(
                    "Parse document files into model-readable Markdown.\n"
                    "\n"
                    "WHEN TO TRIGGER:\n"
                    "  - A previous tool returned one or more file_* references and document text is needed.\n"
                    "  - The user supplied an obvious direct document URL such as PDF, Office, spreadsheet, HTML, JSON, or text.\n"
                    "DO NOT TRIGGER when:\n"
                    "  - The target is a normal HTML web page; use web_fetch or web_crawl.\n"
                    "  - The target is an image, archive, audio, video, executable, model weight, or database file.\n"
                    "\n"
                    "INPUT RULES:\n"
                    "  - Provide exactly one of file_refs or direct_urls.\n"
                    "  - file_refs must be file_* values returned by trusted tools.\n"
                    "  - direct_urls must be complete public http(s) document file URLs.\n"
                    "  - Never invent or pass a local filesystem path.\n"
                    "\n"
                    "OUTPUT RULES:\n"
                    "  - Each input returns an independent success or failure item.\n"
                    "  - Successful document text is returned as Markdown content."
                ),
                parameters_schema=ToolParametersSchema(
                    {
                        "type": "object",
                        "properties": {
                            "file_refs": {
                                "type": "array",
                                "minItems": 1,
                                "items": {
                                    "type": "string",
                                    "minLength": 1,
                                    "pattern": "^file_",
                                },
                                "description": (
                                    "Internal file_* references produced by trusted tools."
                                ),
                            },
                            "direct_urls": {
                                "type": "array",
                                "minItems": 1,
                                "items": {
                                    "type": "string",
                                    "minLength": 1,
                                    "pattern": "^https?://",
                                },
                                "description": (
                                    "Public direct document file URLs."
                                ),
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
                timeout_seconds=DOCUMENT_PARSE_TOOL_TIMEOUT_SECONDS,
                cache_chunked=True,
            ),
        )

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    async def execute(
            self,
            context: dict[str, Any],
            **kwargs: Any,
    ) -> ToolReturn:
        user_id = str(context["user_id"])
        session_id = str(context["session_id"])
        file_refs = tuple(
            str(value).strip()
            for value in kwargs.get("file_refs", ())
        )
        direct_urls = tuple(
            str(value).strip()
            for value in kwargs.get("direct_urls", ())
        )

        if bool(file_refs) == bool(direct_urls):
            raise ToolExecutionError(
                reason="invalid_document_parse_input",
                detail_reason="Provide exactly one of file_refs or direct_urls.",
                retryable=False,
            )

        if file_refs:
            requests = (
                self._parse_file_ref(
                    user_id=user_id,
                    session_id=session_id,
                    file_ref=file_ref,
                )
                for file_ref in file_refs
            )
        else:
            requests = (
                self._parse_direct_url(
                    user_id=user_id,
                    direct_url=direct_url,
                )
                for direct_url in direct_urls
            )

        # 分批 gather 已经限制了并发数，不需要再套一层 Semaphore。
        item_results: list[
            tuple[DocumentParseToolItem, str | None]
        ] = []
        for batch in batched(requests, DOCUMENT_PARSE_CONCURRENCY):
            item_results.extend(await asyncio.gather(*batch))

        return ToolReturn(
            tag="document_parse_result",
            visible_result={
                "items": tuple(item for item, _ in item_results),
            },
            cacheable_texts=tuple(
                markdown
                for _, markdown in item_results
                if markdown
            ),
        )

    async def _parse_file_ref(
            self,
            *,
            user_id: str,
            session_id: str,
            file_ref: str,
    ) -> tuple[DocumentParseToolItem, str | None]:
        try:
            resolved = await self._file_store.resolve_ref(
                user_id=user_id,
                session_id=session_id,
                ref_id=file_ref,
            )
        except Exception as exc:
            return (
                DocumentParseToolItem(
                    source=file_ref,
                    status="failed",
                    reason=file_reference_error_reason(exc),
                ),
                None,
            )

        cache_hit = await self._cache.read_parsed_web_cache(
            user_id=user_id,
            metadata=resolved.metadata,
        )
        if cache_hit is not None:
            return (
                DocumentParseToolItem(
                    source=file_ref,
                    status="success",
                    file_name=resolved.filename,
                ),
                cache_hit,
            )

        return await self._convert_local_file(
            user_id=user_id,
            source=file_ref,
            file_path=resolved.path,
            file_name=resolved.filename,
            content_type=resolved.content_type,
            metadata=resolved.metadata,
        )

    async def _parse_direct_url(
            self,
            *,
            user_id: str,
            direct_url: str,
    ) -> tuple[DocumentParseToolItem, str | None]:
        if self._url_download_http_client is None:
            return (
                DocumentParseToolItem(
                    source=direct_url,
                    status="failed",
                    reason="direct_url_fetch_unavailable",
                ),
                None,
            )

        try:
            url = validate_public_http_url(direct_url.strip())
        except UrlSecurityError as exc:
            return (
                DocumentParseToolItem(
                    source=direct_url,
                    status="failed",
                    reason=f"invalid_direct_url:{exc}",
                ),
                None,
            )

        metadata: dict[str, object] = {
            "source_kind": "web_fetch",
            "source_scope": "web_public",
            "source_url": url,
            "content_type": None,
        }
        cache_hit = await self._cache.read_parsed_web_cache(
            user_id=user_id,
            metadata=metadata,
        )
        if cache_hit is not None:
            return (
                DocumentParseToolItem(
                    source=direct_url,
                    status="success",
                    file_name=filename_from_url(url),
                ),
                cache_hit,
            )

        downloaded: DownloadedUrl | None = None
        try:
            downloaded = await download_url(
                url,
                http_client=self._url_download_http_client,
                max_response_bytes=DOCUMENT_PARSE_MAX_DOWNLOAD_BYTES,
            )
            await self._cache.write_direct_url_cache_stub(
                user_id=user_id,
                raw=downloaded,
            )

            metadata.update({
                "source_url": downloaded.source_url,
                "content_type": downloaded.content_type,
            })
            file_name = (
                filename_from_url(downloaded.source_url)
                or f"download.{downloaded.file_label or 'bin'}"
            )

            return await self._convert_local_file(
                user_id=user_id,
                source=direct_url,
                file_path=Path(downloaded.file_path),
                file_name=file_name,
                content_type=downloaded.content_type,
                metadata=metadata,
            )

        except UrlDownloadUnsupportedUrlError as exc:
            reason = (
                "direct_url_not_file"
                if exc.reason == "url_resolved_to_html"
                else f"direct_url_fetch_failed:{exc.reason}"
            )
            return (
                DocumentParseToolItem(
                    source=direct_url,
                    status="failed",
                    reason=reason,
                ),
                None,
            )

        except UrlDownloadError as exc:
            return (
                DocumentParseToolItem(
                    source=direct_url,
                    status="failed",
                    reason=f"direct_url_fetch_failed:{exc.reason}",
                ),
                None,
            )

        finally:
            # URL 下载器产生的临时文件只在本次解析期间存活。
            if downloaded is not None:
                with contextlib.suppress(OSError):
                    Path(downloaded.file_path).unlink(missing_ok=True)

    async def _convert_local_file(
            self,
            *,
            user_id: str,
            source: str,
            file_path: Path,
            file_name: str,
            content_type: str | None,
            metadata: dict[str, object],
    ) -> tuple[DocumentParseToolItem, str | None]:
        try:
            result = await self._parse_service.parse(
                DocumentParseRequest(
                    file_path=file_path,
                    original_filename=file_name,
                    mime_type=content_type,
                )
            )
            markdown = result.markdown.strip()

            if markdown:
                await self._cache.write_parsed_web_cache(
                    user_id=user_id,
                    metadata=metadata,
                    content_type=content_type,
                    markdown=markdown,
                )

            return (
                DocumentParseToolItem(
                    source=source,
                    status="success",
                    file_name=file_name,
                ),
                markdown or None,
            )

        except Exception as exc:
            return (
                DocumentParseToolItem(
                    source=source,
                    status="failed",
                    file_name=file_name,
                    reason=_document_error_reason(exc),
                ),
                None,
            )


def _document_error_reason(error: BaseException) -> str:
    if isinstance(error, UnsupportedDocumentFormatError):
        return "unsupported_document_format"
    if isinstance(error, DocumentDecodeError):
        return f"document_decode_failed:{error}"
    if isinstance(error, RemoteParserTimeoutError):
        return f"remote_parser_timeout:{error}"
    if isinstance(error, DocumentTooLargeError):
        return f"document_too_large:{error}"
    if isinstance(error, RemoteParserError):
        return f"remote_parser_failed:{error}"
    if isinstance(error, DocumentParseError):
        return f"document_parse_failed:{error}"
    return "document_parse_failed"
