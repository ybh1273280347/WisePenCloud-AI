from __future__ import annotations

from ..models import AdmitFallback, FetchJob, FetchQueue, FetchSlot, HttpxJobHandler


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
