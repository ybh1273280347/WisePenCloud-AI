from __future__ import annotations

from charset_normalizer import from_bytes as detect_encoding
from scrapling.engines.toolbelt.custom import Response

from chat.application.tools.utils.file_type_detect import detect_file_type_from_bytes
from chat.application.tools.utils.url import filename_from_url
from common.logger import warn
from ..core.errors import (
    UrlFetchHttpError,
    UrlFetchNetworkError,
    UrlFetchUnsupportedUrlError,
)
from ..core.models import RawFetchOutput

_HTML_CONTENT_TYPES = {"text/html", "application/xhtml+xml"}
_TYPE_SNIFF_BYTES = 32_768
_HTML_PREFIXES = (b"<!doctype html", b"<html", b"<head", b"<body")


def build_raw_html_output(
        response: Response,
        *,
        source_url: str,
        fetcher: str,
        max_response_bytes: int,
) -> RawFetchOutput:
    """将页面抓取响应适配为内部 HTML 抓取结果。"""
    status = response.status

    if 300 <= status < 400 or response.history or response.url.strip() != source_url:
        raise UrlFetchUnsupportedUrlError(
            url=source_url,
            reason="redirect_not_allowed",
        )

    if status >= 400:
        raise UrlFetchHttpError(url=source_url, reason=f"http {status}")

    body = response.body
    if not body:
        raise UrlFetchNetworkError(url=source_url, reason="empty response body")

    if len(body) > max_response_bytes:
        warn(
            "web_fetch page response exceeded max bytes",
            url=source_url,
            max_bytes=max_response_bytes,
        )
        raise UrlFetchNetworkError(
            url=source_url,
            reason=f"response exceeded max bytes {max_response_bytes}",
        )

    content_type = response.headers.get("content-type")
    if not _is_html(body, content_type, source_url):
        raise UrlFetchUnsupportedUrlError(
            url=source_url,
            reason="url_resolved_to_non_html",
        )

    return RawFetchOutput(
        source_url=source_url,
        fetcher=fetcher,
        status_code=status,
        content_type=content_type,
        headers={str(key): str(value) for key, value in response.headers.items()},
        raw_html=_decode_body(body, response.encoding),
    )


def _is_html(
        body: bytes,
        content_type: str | None,
        source_url: str,
) -> bool:
    media_type = (content_type or "").partition(";")[0].strip().lower()
    if media_type in _HTML_CONTENT_TYPES:
        return True

    file_type = detect_file_type_from_bytes(
        body[:_TYPE_SNIFF_BYTES],
        fallback_name=filename_from_url(source_url),
    )
    if file_type.label == "html" or file_type.mime_type in _HTML_CONTENT_TYPES:
        return True

    return body.lstrip()[:512].lower().startswith(_HTML_PREFIXES)


def _decode_body(raw: bytes, declared_encoding: str | None) -> str:
    if declared_encoding:
        try:
            return raw.decode(declared_encoding, errors="replace")
        except LookupError:
            pass

    detected = detect_encoding(
        raw,
        cp_isolation=["utf-8", "gbk", "big5", "shift_jis", "euc_kr"],
    ).best()
    return str(detected) if detected else raw.decode("utf-8", errors="replace")

