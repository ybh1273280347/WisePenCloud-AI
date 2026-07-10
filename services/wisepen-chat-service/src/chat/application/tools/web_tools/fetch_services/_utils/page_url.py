from __future__ import annotations

from chat.application.tools.utils.url import (
    UrlSecurityError,
    validate_public_http_url_async,
)

from ..core.errors import UrlFetchUnsupportedUrlError


async def validate_page_url(url: str) -> str:
    try:
        return await validate_public_http_url_async(url.strip())
    except UrlSecurityError as exc:
        raise UrlFetchUnsupportedUrlError(url=url, reason=str(exc)) from exc
