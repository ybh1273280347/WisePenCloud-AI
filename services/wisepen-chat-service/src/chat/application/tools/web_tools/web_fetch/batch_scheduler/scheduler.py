from __future__ import annotations

import asyncio

from ..errors import UrlFetchError
from .models import (
    AdmitFallback,
    FallbackAdmission,
    FetchJob,
    FetchSlot,
    HttpxJobHandler,
    ScraplingJobHandler,
)
from .workers import httpx_worker, scrapling_worker


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
                httpx_worker(
                    httpx_queue=httpx_queue,
                    scrapling_queue=scrapling_queue,
                    results=results,
                    admit_fallback=admit_fallback,
                    job_handler=self._httpx_job_handler,
                )
            )
            for _ in range(min(self._httpx_concurrency, len(urls)))
        ]
        scrapling_workers = [
            asyncio.create_task(
                scrapling_worker(
                    scrapling_queue=scrapling_queue,
                    results=results,
                    job_handler=self._scrapling_job_handler,
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
