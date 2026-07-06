from __future__ import annotations

from .models import AdmitFallback, FetchQueue, FetchSlot, HttpxJobHandler, ScraplingJobHandler


async def httpx_worker(
        *,
        httpx_queue: FetchQueue,
        scrapling_queue: FetchQueue,
        results: list[FetchSlot],
        admit_fallback: AdmitFallback,
        job_handler: HttpxJobHandler,
) -> None:
    while True:
        job = await httpx_queue.get()
        try:
            await job_handler(
                job,
                scrapling_queue,
                results,
                admit_fallback,
            )
        finally:
            httpx_queue.task_done()


async def scrapling_worker(
        *,
        scrapling_queue: FetchQueue,
        results: list[FetchSlot],
        job_handler: ScraplingJobHandler,
) -> None:
    while True:
        job = await scrapling_queue.get()
        try:
            results[job.index] = await job_handler(job)
        finally:
            scrapling_queue.task_done()
