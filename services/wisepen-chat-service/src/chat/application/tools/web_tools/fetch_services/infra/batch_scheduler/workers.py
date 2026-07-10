from __future__ import annotations

from .models import AdmitFallback, FetchQueue, FetchSlot, StaticJobHandler, StealthyJobHandler


async def static_worker(
        *,
        static_queue: FetchQueue,
        stealthy_queue: FetchQueue,
        results: list[FetchSlot],
        admit_fallback: AdmitFallback,
        job_handler: StaticJobHandler,
) -> None:
    while True:
        job = await static_queue.get()
        try:
            await job_handler(
                job,
                stealthy_queue,
                results,
                admit_fallback,
            )
        finally:
            static_queue.task_done()


async def stealthy_worker(
        *,
        stealthy_queue: FetchQueue,
        results: list[FetchSlot],
        job_handler: StealthyJobHandler,
) -> None:
    while True:
        job = await stealthy_queue.get()
        try:
            results[job.index] = await job_handler(job)
        finally:
            stealthy_queue.task_done()
