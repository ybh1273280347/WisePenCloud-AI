from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class OpenAlexFailureReason(StrEnum):
    API_KEY_MISSING = "api_key_missing"
    MISSING_LOOKUP_KEY = "missing_lookup_key"
    NOT_FOUND = "not_found"
    RATE_LIMITED = "rate_limited"
    HTTP_ERROR = "http_error"
    NETWORK_ERROR = "network_error"
    INVALID_URL = "invalid_url"
    EMPTY_RESULTS = "empty_results"
    URL_NOT_MATCHED = "url_not_matched"
    AMBIGUOUS_URL = "ambiguous_url"
    EMPTY_TITLE = "empty_title"
    TITLE_NOT_MATCHED = "title_not_matched"
    AMBIGUOUS_TITLE = "ambiguous_title"


@dataclass(frozen=True, slots=True)
class HydratedPaper:
    doi: str | None = None
    publication_year: int | None = None
    cited_by_count: int | None = None
    authors: tuple["HydratedPaperAuthor", ...] = ()
    institutions: tuple[str, ...] = ()
    open_access: "HydratedPaperOpenAccess | None" = None
    failure_reason: OpenAlexFailureReason | None = None


@dataclass(frozen=True, slots=True)
class HydratedPaperAuthor:
    name: str
    institutions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class HydratedPaperOpenAccess:
    is_oa: bool | None = None
    oa_status: str | None = None
    oa_url: str | None = None
