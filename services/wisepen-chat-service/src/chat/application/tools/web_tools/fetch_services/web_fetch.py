from __future__ import annotations

import contextlib
from pathlib import Path

from chat.application.tools.common.tool_run_file_store import ToolRunFileStore
from chat.application.tools.common.tool_run_file_store.core.errors import ToolRunFileStoreError
from chat.application.tools.common.web_content_cache import (
    WebContentCacheRepository,
)
from chat.application.tools.utils.url import filename_from_url
from common.logger import info, warn
from ._utils import judge_quality
from .cleaners.base import BaseCleaner
from .core.errors import UrlFetchError, UrlFetchHttpError, UrlFetchUnsupportedUrlError
from .core.models import RawFetchOutput, WebFetchBatchResult, WebFetchFailure, WebFetchResult
from .downloaders import TempFileDownloader
from .fetchers import WebFetcher
from .infra.batch_scheduler import (
    AdmitFallback,
    FetchBatchCancelled,
    FetchBatchScheduler,
    FetchJob,
    FetchQueue,
    FetchSlot,
)
from .infra.cache import WebFetchCache

_PRODUCER_NAME = "web_fetch"
_NOT_RETRYABLE_HTTP_STATUS_REASONS = {"http 404", "http 410"}


class FetchCoordinator:
    """单点抓取协调器：编排 static → stealthy + 非 HTML 文件下载 + 清洗 + 文件移交。"""

    __slots__ = (
        "_cleaner",
        "_cache",
        "_file_store",
        "_static_fetcher",
        "_stealthy_fetcher",
        "_temp_file_downloader",
        "_min_text_length",
        "_batch_concurrency",
        "_stealthy_concurrency",
        "_max_stealthy_fallbacks",
    )

    def __init__(
            self,
            *,
            static_fetcher: WebFetcher,
            stealthy_fetcher: WebFetcher,
            temp_file_downloader: TempFileDownloader,
            cleaner: BaseCleaner,
            file_store: ToolRunFileStore,
            content_cache_repository: WebContentCacheRepository | None = None,
            min_text_length: int = 200,
            batch_concurrency: int = 16,
            stealthy_concurrency: int = 3,
            max_stealthy_fallbacks: int = 6,
    ) -> None:
        self._static_fetcher = static_fetcher
        self._stealthy_fetcher = stealthy_fetcher
        self._temp_file_downloader = temp_file_downloader
        self._cleaner = cleaner
        self._file_store = file_store
        self._cache = WebFetchCache(
            cleaner_name=cleaner.name,
            repository=content_cache_repository,
        )
        self._min_text_length = min_text_length
        self._batch_concurrency = max(1, int(batch_concurrency))
        self._stealthy_concurrency = max(1, int(stealthy_concurrency))
        self._max_stealthy_fallbacks = max(0, int(max_stealthy_fallbacks))

    async def fetch_many(
            self,
            urls: list[str],
            *,
            user_id: str,
            session_id: str,
            source_scope: str = "web_public",
    ) -> WebFetchBatchResult:
        """批量抓取 URL。

        单个 URL 失败不阻塞其他，转为 WebFetchFailure 加入 failed 列表。
        """
        if not urls:
            return WebFetchBatchResult()

        async def run_static_job(
                job: FetchJob,
                stealthy_queue: FetchQueue,
                results: list[FetchSlot],
                admit_fallback: AdmitFallback,
        ) -> None:
            await self._run_static_job(
                job=job,
                user_id=user_id,
                session_id=session_id,
                source_scope=source_scope,
                results=results,
                stealthy_queue=stealthy_queue,
                admit_fallback=admit_fallback,
            )

        async def run_stealthy_job(job: FetchJob) -> WebFetchResult | WebFetchFailure:
            return await self._run_stealthy_job(
                job=job,
                user_id=user_id,
                source_scope=source_scope,
            )

        scheduler = FetchBatchScheduler(
            static_concurrency=self._batch_concurrency,
            stealthy_concurrency=self._stealthy_concurrency,
            max_stealthy_fallbacks=self._max_stealthy_fallbacks,
            fallback_admission=self._fallback_not_admitted_reason,
            static_job_handler=run_static_job,
            stealthy_job_handler=run_stealthy_job,
        )
        batch_cancelled = False
        try:
            results = await scheduler.run(urls)
        except FetchBatchCancelled as exc:
            batch_cancelled = True
            results = exc.slots

        items = tuple(
            result
            for result in results
            if isinstance(result, WebFetchResult)
        )
        failed = tuple(
            result if isinstance(result, WebFetchFailure)
            else WebFetchFailure(
                url=url,
                reason="fetch_timed_out" if batch_cancelled else "batch_result_missing",
            )
            for url, result in zip(urls, results, strict=True)
            if not isinstance(result, WebFetchResult)
        )

        batch_warnings: list[str] = []
        if failed:
            batch_warnings.append(f"{len(failed)}/{len(urls)} urls failed")
        if batch_cancelled:
            batch_warnings.append("tool timed out; returning completed results")

        return WebFetchBatchResult(
            items=items,
            failed=failed,
            warnings=tuple(batch_warnings),
        )

    async def _run_static_job(
            self,
            *,
            job: FetchJob,
            user_id: str,
            session_id: str,
            source_scope: str,
            results: list[FetchSlot],
            stealthy_queue: FetchQueue,
            admit_fallback: AdmitFallback,
    ) -> None:
        try:
            cached_result = await self._cache.read_result(
                url=job.url,
                user_id=user_id,
            )
            if cached_result is not None:
                results[job.index] = cached_result
                return

            warnings: list[str] = []
            try:
                raw = await self._static_fetcher.fetch(job.url)
            except UrlFetchUnsupportedUrlError as exc:
                if exc.reason != "url_resolved_to_non_html":
                    results[job.index] = WebFetchFailure(url=job.url, reason=exc.reason)
                    return

                raw = await self._temp_file_downloader.download(job.url)
                results[job.index] = await self._handle_non_html_file(
                    raw=raw,
                    user_id=user_id,
                    session_id=session_id,
                    source_scope=source_scope,
                    warnings=warnings,
                )
                return
            except UrlFetchError as exc:
                not_admitted_reason = admit_fallback(exc)
                if not_admitted_reason is not None:
                    results[job.index] = WebFetchFailure(
                        url=job.url,
                        reason=f"fallback_not_admitted: {not_admitted_reason}",
                    )
                    return

                warn("网页抓取 static 失败，投递到 stealthy", url=job.url, reason=exc.reason)
                warnings.append(f"static_fallback: {exc.reason}")
                await stealthy_queue.put(FetchJob(index=job.index, url=job.url, warnings=tuple(warnings)))
                return

            cleaned = self._cleaner.clean(raw.raw_html or "", url=raw.source_url)
            quality = judge_quality(
                raw=raw,
                cleaned=cleaned,
                min_text_length=self._min_text_length,
            )

            if quality.should_fallback:
                not_admitted_reason = admit_fallback()
                if not_admitted_reason is not None:
                    results[job.index] = WebFetchFailure(
                        url=job.url,
                        reason=f"fallback_not_admitted: {not_admitted_reason}",
                    )
                    return

                warn("网页抓取 static 内容质量不足，投递到 stealthy", url=job.url, reason=quality.reason)
                warnings.append(f"static_quality_fallback: {quality.reason}")
                await stealthy_queue.put(FetchJob(index=job.index, url=job.url, warnings=tuple(warnings)))
                return

            result = WebFetchResult(
                source_url=raw.source_url,
                status_code=raw.status_code,
                content_type=raw.content_type,
                title=cleaned.title,
                markdown=cleaned.markdown,
            )
            await self._cache.write_html_result(
                url=job.url,
                user_id=user_id,
                source_scope=source_scope,
                raw=raw,
                result=result,
            )
            results[job.index] = result
        except UrlFetchError as exc:
            results[job.index] = WebFetchFailure(url=job.url, reason=exc.reason)
        except Exception as exc:
            warn("网页抓取 static worker 未预期失败", url=job.url, e=exc)
            results[job.index] = WebFetchFailure(url=job.url, reason=f"unexpected_error: {exc}")

    async def _run_stealthy_job(
            self,
            *,
            job: FetchJob,
            user_id: str,
            source_scope: str,
    ) -> WebFetchResult | WebFetchFailure:
        warnings = list(job.warnings)
        try:
            raw = await self._stealthy_fetcher.fetch(job.url)
            cleaned = self._cleaner.clean(raw.raw_html or "", url=raw.source_url)
            quality = judge_quality(
                raw=raw,
                cleaned=cleaned,
                min_text_length=self._min_text_length,
            )
            if quality.should_fallback:
                warnings.append(f"content quality insufficient: {quality.reason}")

            result = WebFetchResult(
                source_url=raw.source_url,
                status_code=raw.status_code,
                content_type=raw.content_type,
                title=cleaned.title,
                markdown=cleaned.markdown,
                warnings=tuple(warnings),
            )
            if not quality.should_fallback:
                await self._cache.write_html_result(
                    url=job.url,
                    user_id=user_id,
                    source_scope=source_scope,
                    raw=raw,
                    result=result,
                )
            return result
        except UrlFetchError as exc:
            return WebFetchFailure(url=job.url, reason=f"stealthy_failed: {exc.reason}")
        except Exception as exc:
            warn("网页抓取 stealthy worker 未预期失败", url=job.url, e=exc)
            return WebFetchFailure(url=job.url, reason=f"stealthy_failed: {exc}")

    def _fallback_not_admitted_reason(
            self,
            exc: UrlFetchError | None,
            admitted_fallbacks: int,
            fallback_limit: int,
    ) -> str | None:
        if isinstance(exc, UrlFetchUnsupportedUrlError):
            return f"unsupported_url: {exc.reason}"

        if isinstance(exc, UrlFetchHttpError) and exc.reason in _NOT_RETRYABLE_HTTP_STATUS_REASONS:
            return f"http_status_not_retryable: {exc.reason}"

        if admitted_fallbacks >= fallback_limit:
            return "max_stealthy_fallbacks_reached"

        return None

    async def _handle_non_html_file(
            self,
            *,
            raw: RawFetchOutput,
            user_id: str,
            session_id: str,
            source_scope: str,
            warnings: list[str],
    ) -> WebFetchResult:
        """移交非 HTML 文件到 ToolRunFileStore，返回带 file_ref 的结果。"""
        file_path = raw.file_path
        assert file_path is not None  # 由调用方保证

        try:
            filename = (
                    filename_from_url(raw.source_url)
                    or f"download.{raw.file_label or 'bin'}"
            )
            await self._cache.write_non_html_stub(
                user_id=user_id,
                source_scope=source_scope,
                raw=raw,
            )
            record = await self._file_store.publish_file(
                user_id=user_id,
                session_id=session_id,
                producer=_PRODUCER_NAME,
                path=file_path,
                filename=filename,
                content_type=raw.content_type,
                ref_prefix=source_scope,
                metadata={
                    "source_kind": "web_fetch",
                    "source_scope": source_scope,
                    "source_url": raw.source_url,
                    "content_type": raw.content_type,
                },
            )
            info(
                "网页抓取非 HTML 文件已发布为临时文件引用",
                url=raw.source_url,
                ref_id=record.ref_id,
                label=raw.file_label,
            )
            return WebFetchResult(
                source_url=raw.source_url,
                status_code=raw.status_code,
                content_type=raw.content_type,
                title=None,
                markdown=None,
                file_ref=record.ref_id,
                file_label=raw.file_label,
                warnings=tuple(warnings),
            )
        except ToolRunFileStoreError as exc:
            raise UrlFetchError(
                url=raw.source_url,
                reason=f"file_publish_failed: {exc}",
            ) from exc
        finally:
            # 清理临时文件
            with contextlib.suppress(OSError):
                Path(file_path).unlink(missing_ok=True)
