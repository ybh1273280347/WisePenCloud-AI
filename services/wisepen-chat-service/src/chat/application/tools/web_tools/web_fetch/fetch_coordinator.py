from __future__ import annotations

import contextlib
from pathlib import Path

from chat.application.tools.common.tool_run_file_store import ToolRunFileStore
from chat.application.tools.common.tool_run_file_store.errors import ToolRunFileStoreError
from chat.application.tools.common.web_content_cache import (
    WebContentCacheEntryRepository,
    WebContentCacheValueRepository,
)
from chat.application.tools.utils.url import filename_from_url
from common.logger import info, warn
from ._utils import judge_quality
from .batch_scheduler import (
    AdmitFallback,
    FetchBatchScheduler,
    FetchJob,
    FetchQueue,
    FetchSlot,
)
from .cache import WebFetchCache
from .cleaners.base import BaseCleaner
from .errors import UrlFetchError, UrlFetchHttpError, UrlFetchUnsupportedUrlError
from .fetchers import WebFetcher
from .models import RawFetchOutput, WebFetchBatchResult, WebFetchFailure, WebFetchResult

_PRODUCER_NAME = "web_fetch"
_NOT_RETRYABLE_HTTP_STATUS_REASONS = {"http 404", "http 410"}


class FetchCoordinator:
    """单点抓取协调器：编排 httpx → scrapling fallback 链路 + 清洗 + 质量判断 + 文件移交。`WebCrawler` 用于递归爬取。"""

    __slots__ = (
        "_httpx_fetcher",
        "_scrapling_fetcher",
        "_cleaner",
        "_cache",
        "_file_store",
        "_min_text_length",
        "_batch_concurrency",
        "_scrapling_concurrency",
        "_max_scrapling_fallbacks",
    )

    def __init__(
            self,
            *,
            httpx_fetcher: WebFetcher,
            scrapling_fetcher: WebFetcher,
            cleaner: BaseCleaner,
            file_store: ToolRunFileStore,
            content_cache_entry_repository: WebContentCacheEntryRepository | None = None,
            content_cache_value_repository: WebContentCacheValueRepository | None = None,
            min_text_length: int = 200,
            batch_concurrency: int = 5,
            scrapling_concurrency: int = 2,
            max_scrapling_fallbacks: int = 6,
    ) -> None:
        self._httpx_fetcher = httpx_fetcher
        self._scrapling_fetcher = scrapling_fetcher
        self._cleaner = cleaner
        self._file_store = file_store
        self._cache = WebFetchCache(
            cleaner_name=cleaner.name,
            entry_repository=content_cache_entry_repository,
            value_repository=content_cache_value_repository,
        )
        self._min_text_length = min_text_length
        self._batch_concurrency = max(1, int(batch_concurrency))
        self._scrapling_concurrency = max(1, int(scrapling_concurrency))
        self._max_scrapling_fallbacks = max(0, int(max_scrapling_fallbacks))

    async def fetch_one(
            self,
            url: str,
            *,
            user_id: str,
            session_id: str,
            source_scope: str = "web_public",
    ) -> WebFetchResult:
        """抓取单个 URL。

        强制走 httpx → scrapling 链路，不允许跳过。

        Args:
            url: 目标 URL。
            user_id: 用户隔离键（用于 ToolRunFileStore 文件移交）。
            session_id: 会话隔离键（用于 ToolRunFileStore 文件移交）。

        Returns:
            WebFetchResult: 成功结果（HTML 页面或非 HTML 文件引用）。

        Raises:
            UrlFetchError: 抓取失败（HTTP 错误、网络错误、URL 不支持）。
        """
        info("网页抓取开始", url=url)

        cached_result = await self._cache.read_result(
            url=url,
            user_id=user_id,
        )
        if cached_result is not None:
            return cached_result

        # 强制先走 httpx
        warnings: list[str] = []
        try:
            raw = await self._httpx_fetcher.fetch(url)
        except UrlFetchError as exc:
            warn(
                "网页抓取 httpx 失败，降级到 scrapling",
                url=url,
                reason=exc.reason,
            )
            warnings.append(f"httpx_fallback: {exc.reason}")
            raw = await self._scrapling_fetcher.fetch(url)

        # 非 HTML 文件路径：移交 ToolRunFileStore
        if raw.file_path is not None:
            return await self._handle_non_html_file(
                raw=raw,
                user_id=user_id,
                session_id=session_id,
                source_scope=source_scope,
                warnings=warnings,
            )

        # HTML 路径：清洗 + 质量判断
        cleaned = self._cleaner.clean(raw.raw_html or "", url=raw.final_url or url)
        quality = judge_quality(
            raw=raw,
            cleaned=cleaned,
            min_text_length=self._min_text_length,
        )

        if quality.should_fallback:
            # httpx 质量不足，降级到 scrapling
            warn(
                "网页抓取 httpx 内容质量不足，降级到 scrapling",
                url=url,
                reason=quality.reason,
            )
            warnings.append(f"httpx_quality_fallback: {quality.reason}")
            raw = await self._scrapling_fetcher.fetch(url)
            # scrapling 只返回 HTML（非 HTML 已被 httpx 拦截），无需再判 file_path
            cleaned = self._cleaner.clean(
                raw.raw_html or "", url=raw.final_url or url
            )
            quality = judge_quality(
                raw=raw,
                cleaned=cleaned,
                min_text_length=self._min_text_length,
            )

        if quality.should_fallback:
            warnings.append(f"content quality insufficient: {quality.reason}")

        # 不截断 markdown：完整文本保留供后续缓存层处理
        result = WebFetchResult(
            source_url=raw.source_url,
            final_url=raw.final_url,
            status_code=raw.status_code,
            content_type=raw.content_type,
            title=cleaned.title,
            markdown=cleaned.markdown,
            warnings=tuple(warnings),
        )
        if not quality.should_fallback:
            await self._cache.write_html_result(
                url=url,
                user_id=user_id,
                source_scope=source_scope,
                raw=raw,
                result=result,
            )
        return result

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

        async def run_httpx_job(
                job: FetchJob,
                scrapling_queue: FetchQueue,
                results: list[FetchSlot],
                admit_fallback: AdmitFallback,
        ) -> None:
            await self._run_httpx_job(
                job=job,
                user_id=user_id,
                session_id=session_id,
                source_scope=source_scope,
                results=results,
                scrapling_queue=scrapling_queue,
                admit_fallback=admit_fallback,
            )

        async def run_scrapling_job(job: FetchJob) -> WebFetchResult | WebFetchFailure:
            return await self._run_scrapling_job(
                job=job,
                user_id=user_id,
                session_id=session_id,
                source_scope=source_scope,
            )

        scheduler = FetchBatchScheduler(
            httpx_concurrency=self._batch_concurrency,
            scrapling_concurrency=self._scrapling_concurrency,
            max_scrapling_fallbacks=self._max_scrapling_fallbacks,
            fallback_admission=self._fallback_not_admitted_reason,
            httpx_job_handler=run_httpx_job,
            scrapling_job_handler=run_scrapling_job,
        )
        results = await scheduler.run(urls)

        items = tuple(
            result
            for result in results
            if isinstance(result, WebFetchResult)
        )
        failed = tuple(
            result if isinstance(result, WebFetchFailure)
            else WebFetchFailure(url=url, reason="batch_result_missing")
            for url, result in zip(urls, results, strict=True)
            if not isinstance(result, WebFetchResult)
        )

        batch_warnings: list[str] = []
        if failed:
            batch_warnings.append(f"{len(failed)}/{len(urls)} urls failed")

        return WebFetchBatchResult(
            items=items,
            failed=failed,
            warnings=tuple(batch_warnings),
        )

    async def _run_httpx_job(
            self,
            *,
            job: FetchJob,
            user_id: str,
            session_id: str,
            source_scope: str,
            results: list[FetchSlot],
            scrapling_queue: FetchQueue,
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
                raw = await self._httpx_fetcher.fetch(job.url)
            except UrlFetchError as exc:
                not_admitted_reason = admit_fallback(exc)
                if not_admitted_reason is not None:
                    results[job.index] = WebFetchFailure(
                        url=job.url,
                        reason=f"fallback_not_admitted: {not_admitted_reason}",
                    )
                    return

                warn("网页抓取 httpx 失败，投递到 scrapling 慢路径", url=job.url, reason=exc.reason)
                warnings.append(f"httpx_fallback: {exc.reason}")
                await scrapling_queue.put(FetchJob(index=job.index, url=job.url, warnings=tuple(warnings)))
                return

            if raw.file_path is not None:
                results[job.index] = await self._handle_non_html_file(
                    raw=raw,
                    user_id=user_id,
                    session_id=session_id,
                    source_scope=source_scope,
                    warnings=warnings,
                )
                return

            cleaned = self._cleaner.clean(raw.raw_html or "", url=raw.final_url or job.url)
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

                warn("网页抓取 httpx 内容质量不足，投递到 scrapling 慢路径", url=job.url, reason=quality.reason)
                warnings.append(f"httpx_quality_fallback: {quality.reason}")
                await scrapling_queue.put(FetchJob(index=job.index, url=job.url, warnings=tuple(warnings)))
                return

            result = WebFetchResult(
                source_url=raw.source_url,
                final_url=raw.final_url,
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
            warn("网页抓取 httpx worker 未预期失败", url=job.url, e=exc)
            results[job.index] = WebFetchFailure(url=job.url, reason=f"unexpected_error: {exc}")

    async def _run_scrapling_job(
            self,
            *,
            job: FetchJob,
            user_id: str,
            session_id: str,
            source_scope: str,
    ) -> WebFetchResult | WebFetchFailure:
        warnings = list(job.warnings)
        try:
            raw = await self._scrapling_fetcher.fetch(job.url)
            if raw.file_path is not None:
                return await self._handle_non_html_file(
                    raw=raw,
                    user_id=user_id,
                    session_id=session_id,
                    source_scope=source_scope,
                    warnings=warnings,
                )

            cleaned = self._cleaner.clean(raw.raw_html or "", url=raw.final_url or job.url)
            quality = judge_quality(
                raw=raw,
                cleaned=cleaned,
                min_text_length=self._min_text_length,
            )
            if quality.should_fallback:
                warnings.append(f"content quality insufficient: {quality.reason}")

            result = WebFetchResult(
                source_url=raw.source_url,
                final_url=raw.final_url,
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
            return WebFetchFailure(url=job.url, reason=f"scrapling_failed: {exc.reason}")
        except Exception as exc:
            warn("网页抓取 scrapling worker 未预期失败", url=job.url, e=exc)
            return WebFetchFailure(url=job.url, reason=f"scrapling_failed: {exc}")

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
            return "max_scrapling_fallbacks_reached"

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
                    filename_from_url(raw.final_url or raw.source_url)
                    or f"download.{raw.file_label or 'bin'}"
            )
            cache_doc_id = await self._cache.write_non_html_stub(
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
                    "final_url": raw.final_url,
                    "content_type": raw.content_type,
                    "source_cache_doc_id": cache_doc_id,
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
                final_url=raw.final_url,
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
