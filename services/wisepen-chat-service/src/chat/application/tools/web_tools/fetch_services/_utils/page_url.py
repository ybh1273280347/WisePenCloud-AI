from __future__ import annotations

from chat.application.tools.utils.url import UrlSecurityError, validate_public_http_url

from ..core.errors import UrlFetchUnsupportedUrlError


def validate_page_url(url: str) -> str:
    try:
        return validate_public_http_url(url.strip())
    except UrlSecurityError as exc:
        raise UrlFetchUnsupportedUrlError(url=url, reason=str(exc)) from exc
