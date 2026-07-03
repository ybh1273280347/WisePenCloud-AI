from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from chat.application.tools.common.web_content_cache.models import (
    WebContentCacheCleanupResult,
    WebContentCacheMode,
)
from chat.application.tools.common.web_content_cache.repository import (
    WebContentCacheEntryRepository,
)
from chat.application.tools.tool_settings import tool_settings
from chat.domain.entities.web_content_cache import WebContentCacheValueDocument
from common.logger import info, warn


class WebContentCacheGcScheduler:
    """定期清理 MongoDB 中不再 active 的 URL 缓存正文。

    Redis entry 是缓存 active 状态的权威索引。Mongo value 只有在超过保留期、
    且同 URL/mode 下的 Redis entry 不再指向该 doc_id 时才会被删除。
    """

    __slots__ = (
        "_batch_size",
        "_entry_repository",
        "_interval_seconds",
        "_retention_seconds",
        "_task",
    )

    def __init__(
            self,
            *,
            entry_repository: WebContentCacheEntryRepository,
            interval_seconds: int = tool_settings.WEB_CONTENT_CACHE_CLEANUP_INTERVAL_SECONDS,
            retention_seconds: int = tool_settings.WEB_CONTENT_CACHE_INACTIVE_RETENTION_SECONDS,
            batch_size: int = tool_settings.WEB_CONTENT_CACHE_CLEANUP_BATCH_SIZE,
    ) -> None:
        self._entry_repository = entry_repository
        self._interval_seconds = max(1, int(interval_seconds))
        self._retention_seconds = max(1, int(retention_seconds))
        self._batch_size = max(1, int(batch_size))
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(
                self._run_loop(),
                name="web-content-cache-gc",
            )
            info(
                "web content cache gc scheduler started.",
                interval_seconds=self._interval_seconds,
                retention_seconds=self._retention_seconds,
                batch_size=self._batch_size,
            )

    async def stop(self) -> None:
        if self._task is None:
            return

        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None
            info("web content cache gc scheduler stopped.")

    async def cleanup_once(self) -> WebContentCacheCleanupResult:
        """删除已经没有 active Redis entry 指向的 Mongo cache value。"""
        updated_before = datetime.now(timezone.utc) - timedelta(seconds=self._retention_seconds)

        scanned = deleted = active = failed = 0
        cursor = (
            WebContentCacheValueDocument
            .find(WebContentCacheValueDocument.updated_at < updated_before)
            .sort("+updated_at")
            .limit(max(1, self._batch_size))
        )
        documents = await cursor.to_list()

        for document in documents:
            scanned += 1
            try:
                doc_id = str(document.id)
                entry = await self._entry_repository.get_entry(
                    user_id=document.user_id,
                    url=document.canonical_url,
                    cache_mode=WebContentCacheMode(document.cache_mode),
                )
                if entry is not None and entry.mongo_doc_id == doc_id:
                    active += 1
                    continue

                await document.delete()
                deleted += 1
            except Exception:
                failed += 1

        return WebContentCacheCleanupResult(
            scanned=scanned,
            deleted=deleted,
            active=active,
            failed=failed,
        )

    async def _run_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._interval_seconds)
                result = await self.cleanup_once()
                info(
                    "web content cache gc finished.",
                    scanned=result.scanned,
                    deleted=result.deleted,
                    active=result.active,
                    failed=result.failed,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                warn("web content cache gc failed.", e=exc)
