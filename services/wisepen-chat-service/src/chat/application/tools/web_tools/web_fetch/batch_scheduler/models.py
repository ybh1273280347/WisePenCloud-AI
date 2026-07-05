from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from ..errors import UrlFetchError
from ..models import WebFetchFailure, WebFetchResult

FetchOutcome = WebFetchResult | WebFetchFailure
FetchSlot = FetchOutcome | None
AdmitFallback = Callable[[UrlFetchError | None], str | None]
FallbackAdmission = Callable[[UrlFetchError | None, int, int], str | None]


@dataclass(frozen=True, slots=True)
class FetchJob:
    index: int
    url: str
    warnings: tuple[str, ...] = ()


FetchQueue = asyncio.Queue[FetchJob]

HttpxJobHandler = Callable[
    [FetchJob, FetchQueue, list[FetchSlot], AdmitFallback],
    Awaitable[None],
]

ScraplingJobHandler = Callable[[FetchJob], Awaitable[FetchOutcome]]
