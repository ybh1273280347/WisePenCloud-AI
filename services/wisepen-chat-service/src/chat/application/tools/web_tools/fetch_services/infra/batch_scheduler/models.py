from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from ...core.errors import UrlFetchError
from ...core.models import WebFetchFailure, WebFetchResult

FetchOutcome = WebFetchResult | WebFetchFailure
FetchSlot = FetchOutcome | None
AdmitFallback = Callable[[UrlFetchError | None], str | None]
FallbackAdmission = Callable[[UrlFetchError | None, int, int], str | None]


@dataclass(frozen=True, slots=True)
class FetchJob:
    index: int
    url: str
    warnings: tuple[str, ...] = ()


class FetchBatchCancelled(Exception):
    def __init__(self, *, slots: list[FetchSlot]) -> None:
        super().__init__("fetch batch cancelled")
        self.slots = slots


FetchQueue = asyncio.Queue[FetchJob]

StaticJobHandler = Callable[
    [FetchJob, FetchQueue, list[FetchSlot], AdmitFallback],
    Awaitable[None],
]

StealthyJobHandler = Callable[[FetchJob], Awaitable[FetchOutcome]]
