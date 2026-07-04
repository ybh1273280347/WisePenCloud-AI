from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from .errors import UrlFetchError
from .models import WebFetchFailure, WebFetchResult

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


class FetchBatchScheduler:
    """web_fetch 批量抓取的两阶段调度器。

    只负责 httpx 快路径与 scrapling 慢路径的资源池隔离；具体抓取、清洗、
    缓存写入和失败语义仍由 FetchCoordinator 提供。
    """

    __slots__ = (
        "_fallback_admission",
        "_httpx_concurrency",
        "_httpx_job_handler",
        "_max_scrapling_fallbacks",
        "_scrapling_concurrency",
        "_scrapling_job_handler",
    )

    def __init__(
            self,
            *,
            httpx_concurrency: int,
            scrapling_concurrency: int,
            max_scrapling_fallbacks: int,
            fallback_admission: FallbackAdmission,
            httpx_job_handler: HttpxJobHandler,
            scrapling_job_handler: ScraplingJobHandler,
    ) -> None:
        self._httpx_concurrency = max(1, int(httpx_concurrency))
        self._scrapling_concurrency = max(1, int(scrapling_concurrency))
        self._max_scrapling_fallbacks = max(0, int(max_scrapling_fallbacks))
        self._fallback_admission = fallback_admission
        self._httpx_job_handler = httpx_job_handler
        self._scrapling_job_handler = scrapling_job_handler

    async def run(self, urls: list[str]) -> list[FetchSlot]:
        if not urls:
            return []

        httpx_queue: asyncio.Queue[FetchJob] = asyncio.Queue()
        scrapling_queue: asyncio.Queue[FetchJob] = asyncio.Queue()
        results: list[FetchSlot] = [None] * len(urls)
        fallback_limit = min(self._max_scrapling_fallbacks, len(urls))
        admitted_fallbacks = 0

        for index, url in enumerate(urls):
            await httpx_queue.put(FetchJob(index=index, url=url))

        def admit_fallback(exc: UrlFetchError | None = None) -> str | None:
            nonlocal admitted_fallbacks
            not_admitted_reason = self._fallback_admission(
                exc,
                admitted_fallbacks,
                fallback_limit,
            )
            if not_admitted_reason is not None:
                return not_admitted_reason

            admitted_fallbacks += 1
            return None

        httpx_workers = [
            asyncio.create_task(
                self._httpx_worker(
                    httpx_queue=httpx_queue,
                    scrapling_queue=scrapling_queue,
                    results=results,
                    admit_fallback=admit_fallback,
                )
            )
            for _ in range(min(self._httpx_concurrency, len(urls)))
        ]
        scrapling_workers = [
            asyncio.create_task(
                self._scrapling_worker(
                    scrapling_queue=scrapling_queue,
                    results=results,
                )
            )
            for _ in range(min(self._scrapling_concurrency, fallback_limit))
        ]

        try:
            await httpx_queue.join()
            await scrapling_queue.join()
        finally:
            for task in (*httpx_workers, *scrapling_workers):
                task.cancel()
            await asyncio.gather(*httpx_workers, *scrapling_workers, return_exceptions=True)

        return results

    async def _httpx_worker(
            self,
            *,
            httpx_queue: asyncio.Queue[FetchJob],
            scrapling_queue: asyncio.Queue[FetchJob],
            results: list[FetchSlot],
            admit_fallback: AdmitFallback,
    ) -> None:
        while True:
            job = await httpx_queue.get()
            try:
                await self._httpx_job_handler(
                    job,
                    scrapling_queue,
                    results,
                    admit_fallback,
                )
            finally:
                httpx_queue.task_done()

    async def _scrapling_worker(
            self,
            *,
            scrapling_queue: asyncio.Queue[FetchJob],
            results: list[FetchSlot],
    ) -> None:
        while True:
            job = await scrapling_queue.get()
            try:
                results[job.index] = await self._scrapling_job_handler(job)
            finally:
                scrapling_queue.task_done()
