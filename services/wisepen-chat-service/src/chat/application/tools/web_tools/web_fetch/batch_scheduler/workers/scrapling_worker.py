from __future__ import annotations

from ..models import FetchJob, FetchOutcome, FetchQueue, FetchSlot, ScraplingJobHandler


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
