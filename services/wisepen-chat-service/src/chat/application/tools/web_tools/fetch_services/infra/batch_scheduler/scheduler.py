from __future__ import annotations

import asyncio

from .models import (
    FallbackAdmission,
    FetchBatchCancelled,
    FetchJob,
    FetchSlot,
    StaticJobHandler,
    StealthyJobHandler,
)
from .workers import static_worker, stealthy_worker
from ...core.errors import UrlFetchError


class FetchBatchScheduler:
    """web_fetch 批量抓取的两阶段调度器。

    只负责 static 与 stealthy 页面抓取的资源池隔离；具体抓取、清洗、
    缓存写入和失败语义仍由 FetchCoordinator 提供。
    """

    __slots__ = (
        "_fallback_admission",
        "_max_stealthy_fallbacks",
        "_static_concurrency",
        "_static_job_handler",
        "_stealthy_concurrency",
        "_stealthy_job_handler",
    )

    def __init__(
            self,
            *,
            static_concurrency: int,
            stealthy_concurrency: int,
            max_stealthy_fallbacks: int,
            fallback_admission: FallbackAdmission,
            static_job_handler: StaticJobHandler,
            stealthy_job_handler: StealthyJobHandler,
    ) -> None:
        self._static_concurrency = max(1, int(static_concurrency))
        self._stealthy_concurrency = max(1, int(stealthy_concurrency))
        self._max_stealthy_fallbacks = max(0, int(max_stealthy_fallbacks))
        self._fallback_admission = fallback_admission
        self._static_job_handler = static_job_handler
        self._stealthy_job_handler = stealthy_job_handler

    async def run(self, urls: list[str]) -> list[FetchSlot]:
        if not urls:
            return []

        static_queue: asyncio.Queue[FetchJob] = asyncio.Queue()
        stealthy_queue: asyncio.Queue[FetchJob] = asyncio.Queue()
        results: list[FetchSlot] = [None] * len(urls)
        fallback_limit = min(self._max_stealthy_fallbacks, len(urls))
        admitted_fallbacks = 0

        for index, url in enumerate(urls):
            await static_queue.put(FetchJob(index=index, url=url))

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

        static_workers = [
            asyncio.create_task(
                static_worker(
                    static_queue=static_queue,
                    stealthy_queue=stealthy_queue,
                    results=results,
                    admit_fallback=admit_fallback,
                    job_handler=self._static_job_handler,
                )
            )
            for _ in range(min(self._static_concurrency, len(urls)))
        ]
        stealthy_workers = [
            asyncio.create_task(
                stealthy_worker(
                    stealthy_queue=stealthy_queue,
                    results=results,
                    job_handler=self._stealthy_job_handler,
                )
            )
            for _ in range(min(self._stealthy_concurrency, fallback_limit))
        ]

        try:
            await static_queue.join()
            await stealthy_queue.join()
        except asyncio.CancelledError as exc:
            raise FetchBatchCancelled(slots=results) from exc
        finally:
            for task in (*static_workers, *stealthy_workers):
                task.cancel()
            await asyncio.gather(*static_workers, *stealthy_workers, return_exceptions=True)

        return results
