from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256

from common.logger import info, warn
from .cache_ttl import compute_ttl
from .metadata import string_metadata
from .models import (
    WebContentCacheEntry,
    WebContentCacheMode,
    WebContentCacheValue,
)
from .refresh_queue import (
    WEB_FETCH_REFRESH_JOB,
    WebContentCacheRefreshJob,
    WebContentCacheRefreshTaskPublisher,
)
from .repository import (
    WebContentCacheEntryRepository,
    WebContentCacheValueRepository,
)

WEB_PUBLIC_SOURCE_SCOPE = "web_public"
WEB_CUSTOM_SOURCE_SCOPE = "web_custom"
DEFAULT_REFRESH_LOCK_TTL_SECONDS = 300


@dataclass(frozen=True, slots=True)
class CachedMarkdownPage:
    """URL 缓存命中的 HTML/Markdown 页面。"""

    source_url: str
    final_url: str | None
    status_code: int | None
    content_type: str | None
    title: str | None
    markdown: str
    raw_html: str | None
    cache_mode: WebContentCacheMode
    stale: bool


@dataclass(frozen=True, slots=True)
class HtmlCacheWrite:
    """写入 URL HTML 缓存所需的最小数据。"""

    url: str
    user_id: str
    source_scope: str
    final_url: str | None
    status_code: int | None
    content_type: str | None
    raw_html: str | None
    markdown: str
    title: str | None
    headers: dict[str, str]
    fetcher: str | None
    cleaner: str | None
    producer: str
    extra_metadata: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class NonHtmlCacheStubWrite:
    """写入非 HTML 文件占位缓存所需的最小数据。"""

    user_id: str
    source_scope: str
    source_url: str
    final_url: str | None
    status_code: int | None
    content_type: str | None
    headers: dict[str, str]
    fetcher: str | None
    file_label: str | None
    source_kind: str = "web_fetch"
    extra_metadata: dict[str, object] | None = None


class WebContentCacheService:
    """URL 内容缓存门面，封装 HTML markdown 读写与 stale refresh 调度。"""

    __slots__ = ("_entry_repository", "_value_repository", "_refresh_task_publisher")

    def __init__(
            self,
            *,
            entry_repository: WebContentCacheEntryRepository | None,
            value_repository: WebContentCacheValueRepository | None,
            refresh_task_publisher: WebContentCacheRefreshTaskPublisher | None = None,
    ) -> None:
        self._entry_repository = entry_repository
        self._value_repository = value_repository
        self._refresh_task_publisher = refresh_task_publisher

    async def read_markdown_page(
            self,
            *,
            url: str,
            user_id: str,
            session_id: str,
            refresh_job_prefix: str,
            refresh_task_name: str = WEB_FETCH_REFRESH_JOB,
            refresh_lock_ttl_seconds: int = DEFAULT_REFRESH_LOCK_TTL_SECONDS,
    ) -> CachedMarkdownPage | None:
        """读取 URL markdown 缓存，stale 命中时返回旧内容并安排后台刷新。"""
        entry_repository = self._entry_repository
        value_repository = self._value_repository
        if entry_repository is None or value_repository is None:
            return None

        try:
            now = datetime.now(timezone.utc)
            for mode in (WebContentCacheMode.PRIVATE, WebContentCacheMode.PUBLIC):
                entry = await entry_repository.get_entry(
                    user_id=user_id,
                    url=url,
                    cache_mode=mode,
                )
                if entry is None:
                    continue

                value = await value_repository.get_value(doc_id=entry.mongo_doc_id)
                if value is None or not value.markdown:
                    continue

                hard_expire_at = _ensure_aware(entry.hard_expire_at)
                if now > hard_expire_at:
                    continue

                title = value.metadata.get("title")
                stale = now > _ensure_aware(entry.soft_expire_at)
                if stale:
                    refresh_source_scope = (
                        WEB_CUSTOM_SOURCE_SCOPE
                        if entry.cache_mode == WebContentCacheMode.PRIVATE
                        else WEB_PUBLIC_SOURCE_SCOPE
                    )
                    await self.schedule_stale_refresh(
                        url=url,
                        user_id=user_id,
                        session_id=session_id,
                        source_scope=refresh_source_scope,
                        cache_mode=entry.cache_mode,
                        refresh_job_prefix=refresh_job_prefix,
                        refresh_task_name=refresh_task_name,
                        refresh_lock_ttl_seconds=refresh_lock_ttl_seconds,
                    )

                info(
                    "URL markdown 缓存命中",
                    url=url,
                    cache_mode=entry.cache_mode.value,
                    doc_id=entry.mongo_doc_id,
                    stale=stale,
                    producer=refresh_job_prefix,
                )
                return CachedMarkdownPage(
                    source_url=url,
                    final_url=value.final_url,
                    status_code=value.status_code,
                    content_type=value.content_type,
                    title=title if isinstance(title, str) else None,
                    markdown=value.markdown,
                    raw_html=value.raw_html,
                    cache_mode=entry.cache_mode,
                    stale=stale,
                )
        except Exception as exc:
            warn("URL markdown 缓存读取失败，降级为实时获取", url=url, e=exc)

        return None

    async def write_html_markdown(self, write: HtmlCacheWrite) -> str | None:
        """写入 HTML 清洗结果缓存；失败返回 None，不影响调用方结果。"""
        entry_repository = self._entry_repository
        value_repository = self._value_repository
        if entry_repository is None or value_repository is None or not write.markdown:
            return None

        try:
            now = datetime.now(timezone.utc)
            mode = _cache_mode_for_source_scope(write.source_scope)
            ttl = compute_ttl(
                headers=write.headers,
                now=now,
                is_shared_cache=(mode == WebContentCacheMode.PUBLIC),
                status_code=write.status_code or 200,
            )
            if ttl.no_store:
                info("URL HTML 缓存被 no-store 指令跳过", url=write.url)
                return None

            canonical_url = write.url.strip()
            content_hash_payload = f"{write.raw_html or ''}\n---markdown---\n{write.markdown}"
            metadata = {
                "title": write.title,
                "source_scope": write.source_scope,
                "source_url": write.url,
                "fetcher": write.fetcher,
                "cleaner": write.cleaner,
                "producer": write.producer,
                "cache_control": write.headers.get("cache-control"),
                **(write.extra_metadata or {}),
            }
            value = WebContentCacheValue(
                id=None,
                user_id=write.user_id,
                canonical_url=canonical_url,
                final_url=write.final_url,
                cache_mode=mode,
                status_code=write.status_code,
                content_type=write.content_type,
                raw_html=write.raw_html,
                markdown=write.markdown,
                content_hash=sha256(content_hash_payload.encode("utf-8")).hexdigest(),
                fetched_at=now,
                metadata=metadata,
            )
            doc_id = await value_repository.save_value(value)
            await entry_repository.set_entry(
                WebContentCacheEntry(
                    user_id=write.user_id,
                    url_hash=sha256(canonical_url.encode("utf-8")).hexdigest(),
                    canonical_url=canonical_url,
                    mongo_doc_id=doc_id,
                    cache_mode=mode,
                    soft_expire_at=ttl.soft_expire_at,
                    hard_expire_at=ttl.hard_expire_at,
                    etag=write.headers.get("etag"),
                    last_modified=write.headers.get("last-modified"),
                )
            )
            info(
                "URL HTML 缓存已写入",
                url=write.url,
                cache_mode=mode.value,
                doc_id=doc_id,
                producer=write.producer,
            )
            return doc_id
        except Exception as exc:
            warn("URL HTML 缓存写入失败", url=write.url, e=exc)
            return None

    async def write_non_html_stub(self, write: NonHtmlCacheStubWrite) -> str | None:
        """为非 HTML 文件预创建 URL 缓存文档，供后续 parser 回写 markdown。"""
        entry_repository = self._entry_repository
        value_repository = self._value_repository
        if entry_repository is None or value_repository is None:
            return None

        try:
            now = datetime.now(timezone.utc)
            mode = _cache_mode_for_source_scope(write.source_scope)
            ttl = compute_ttl(
                headers=write.headers,
                now=now,
                is_shared_cache=(mode == WebContentCacheMode.PUBLIC),
                status_code=write.status_code or 200,
            )
            if ttl.no_store:
                info("URL 非 HTML 缓存被 no-store 指令跳过", url=write.source_url)
                return None

            canonical_url = write.source_url.strip()
            value = WebContentCacheValue(
                id=None,
                user_id=write.user_id,
                canonical_url=canonical_url,
                final_url=write.final_url,
                cache_mode=mode,
                status_code=write.status_code,
                content_type=write.content_type,
                raw_html=None,
                markdown=None,
                fetched_at=now,
                metadata={
                    "source_kind": write.source_kind,
                    "source_scope": write.source_scope,
                    "source_url": write.source_url,
                    "final_url": write.final_url,
                    "fetcher": write.fetcher,
                    "file_label": write.file_label,
                    "cache_control": write.headers.get("cache-control"),
                    **(write.extra_metadata or {}),
                },
            )
            doc_id = await value_repository.save_value(value)
            await entry_repository.set_entry(
                WebContentCacheEntry(
                    user_id=write.user_id,
                    url_hash=sha256(canonical_url.encode("utf-8")).hexdigest(),
                    canonical_url=canonical_url,
                    mongo_doc_id=doc_id,
                    cache_mode=mode,
                    soft_expire_at=ttl.soft_expire_at,
                    hard_expire_at=ttl.hard_expire_at,
                    etag=write.headers.get("etag"),
                    last_modified=write.headers.get("last-modified"),
                )
            )
            info("URL 非 HTML 缓存占位已写入", url=write.source_url, cache_mode=mode.value, doc_id=doc_id)
            return doc_id
        except Exception as exc:
            warn("URL 非 HTML 缓存占位写入失败", url=write.source_url, e=exc)
            return None

    async def read_markdown_by_metadata(
            self,
            *,
            user_id: str,
            metadata: dict[str, object],
            parser_version: str | None = None,
    ) -> CachedMarkdownPage | None:
        """按 metadata 中的 URL/source_scope 精确读取 markdown 缓存，不做 public/private 回退。"""
        entry_repository = self._entry_repository
        value_repository = self._value_repository
        if entry_repository is None or value_repository is None:
            return None

        source_kind = string_metadata(metadata, "source_kind")
        source_scope = string_metadata(metadata, "source_scope")
        source_url = string_metadata(metadata, "source_url")
        if source_kind != "web_fetch" or source_scope is None or source_url is None:
            return None

        try:
            now = datetime.now(timezone.utc)
            mode = _cache_mode_for_source_scope(source_scope)
            entry = await entry_repository.get_entry(
                user_id=user_id,
                url=source_url,
                cache_mode=mode,
            )
            if entry is None:
                return None

            hard_expire_at = _ensure_aware(entry.hard_expire_at)
            if now > hard_expire_at:
                return None

            value = await value_repository.get_value(doc_id=entry.mongo_doc_id)
            if value is None or not value.markdown:
                return None
            if parser_version is not None and value.metadata.get("parser_version") != parser_version:
                return None

            title = value.metadata.get("title")
            return CachedMarkdownPage(
                source_url=source_url,
                final_url=value.final_url,
                status_code=value.status_code,
                content_type=value.content_type,
                title=title if isinstance(title, str) else None,
                markdown=value.markdown,
                raw_html=value.raw_html,
                cache_mode=entry.cache_mode,
                stale=now > _ensure_aware(entry.soft_expire_at),
            )
        except Exception as exc:
            warn("URL metadata markdown 缓存读取失败", source_url=source_url, e=exc)
            return None

    async def write_markdown_from_metadata(
            self,
            *,
            user_id: str,
            metadata: dict[str, object],
            content_type: str | None,
            markdown: str,
            parser: str,
            parser_version: str,
    ) -> str | None:
        """回写非 HTML parser 结果到已有 URL 缓存文档。"""
        entry_repository = self._entry_repository
        value_repository = self._value_repository
        if entry_repository is None or value_repository is None or not markdown:
            return None

        source_kind = string_metadata(metadata, "source_kind")
        source_scope = string_metadata(metadata, "source_scope")
        source_url = string_metadata(metadata, "source_url")
        if source_kind != "web_fetch" or source_scope is None or source_url is None:
            return None

        try:
            now = datetime.now(timezone.utc)
            mode = _cache_mode_for_source_scope(source_scope)
            doc_id = string_metadata(metadata, "source_cache_doc_id")
            existing = await value_repository.get_value(doc_id=doc_id) if doc_id else None
            cache_control_header = None
            if existing is not None and isinstance(existing.metadata, dict):
                cache_control_header = existing.metadata.get("cache_control")
            ttl = compute_ttl(
                headers={"cache-control": cache_control_header} if cache_control_header else {},
                now=now,
                is_shared_cache=(mode == WebContentCacheMode.PUBLIC),
                status_code=existing.status_code if existing is not None else 200,
            )
            if ttl.no_store:
                return None

            raw_html = existing.raw_html if existing is not None else None
            final_url = string_metadata(metadata, "final_url")
            content_hash_payload = f"{raw_html or ''}\n---markdown---\n{markdown}"
            value = WebContentCacheValue(
                id=doc_id if existing is not None else None,
                user_id=user_id,
                canonical_url=existing.canonical_url if existing is not None else source_url.strip(),
                final_url=existing.final_url if existing is not None else final_url,
                cache_mode=mode,
                status_code=existing.status_code if existing is not None else None,
                content_type=existing.content_type if existing is not None else content_type,
                raw_html=raw_html,
                markdown=markdown,
                content_hash=sha256(content_hash_payload.encode("utf-8")).hexdigest(),
                fetched_at=existing.fetched_at if existing is not None else now,
                metadata={
                    **(existing.metadata if existing is not None else {}),
                    "source_kind": source_kind,
                    "source_scope": source_scope,
                    "source_url": source_url,
                    "final_url": final_url,
                    "content_type": content_type,
                    "parser": parser,
                    "parser_version": parser_version,
                },
            )
            saved_doc_id = await value_repository.save_value(value)
            await entry_repository.set_entry(
                WebContentCacheEntry(
                    user_id=user_id,
                    url_hash=sha256(value.canonical_url.encode("utf-8")).hexdigest(),
                    canonical_url=value.canonical_url,
                    mongo_doc_id=saved_doc_id,
                    cache_mode=mode,
                    soft_expire_at=ttl.soft_expire_at,
                    hard_expire_at=ttl.hard_expire_at,
                )
            )
            info("URL parser markdown 已回写缓存", source_url=source_url, cache_mode=mode.value, doc_id=saved_doc_id)
            return saved_doc_id
        except Exception as exc:
            warn("URL parser markdown 回写缓存失败", source_url=source_url, e=exc)
            return None

    async def schedule_stale_refresh(
            self,
            *,
            url: str,
            user_id: str,
            session_id: str,
            source_scope: str,
            cache_mode: WebContentCacheMode,
            refresh_job_prefix: str,
            payload: dict[str, object] | None = None,
            refresh_identity_suffix: str | None = None,
            refresh_task_name: str = WEB_FETCH_REFRESH_JOB,
            refresh_lock_ttl_seconds: int = DEFAULT_REFRESH_LOCK_TTL_SECONDS,
    ) -> None:
        entry_repository = self._entry_repository
        if entry_repository is None:
            return

        try:
            lock_owner = "public" if cache_mode == WebContentCacheMode.PUBLIC else user_id
            lock_suffix = f":{refresh_identity_suffix}" if refresh_identity_suffix else ""
            lock_key = f"{refresh_job_prefix}:{cache_mode.value}:{lock_owner}:{url}{lock_suffix}"
            if not await entry_repository.try_acquire_refresh_lock(
                    key=lock_key,
                    ttl_seconds=refresh_lock_ttl_seconds,
            ):
                return
        except Exception as exc:
            warn("URL 缓存 stale 刷新锁获取失败", url=url, e=exc)
            return

        if self._refresh_task_publisher is None:
            return

        url_hash = sha256(url.encode("utf-8")).hexdigest()
        job_id = (
            f"{refresh_job_prefix}:{cache_mode.value}:"
            f"{'public' if cache_mode == WebContentCacheMode.PUBLIC else user_id}:"
            f"{url_hash}{f':{refresh_identity_suffix}' if refresh_identity_suffix else ''}"
        )
        try:
            await self._refresh_task_publisher.enqueue(
                WebContentCacheRefreshJob(
                    name=refresh_task_name,
                    job_id=job_id,
                    payload=payload
                            or {
                                "url": url,
                                "user_id": user_id,
                                "session_id": session_id,
                                "source_scope": source_scope,
                                "cache_mode": cache_mode.value,
                            },
                )
            )
        except Exception as exc:
            warn("URL 缓存 stale 刷新任务入队失败", url=url, e=exc)


def _cache_mode_for_source_scope(source_scope: str) -> WebContentCacheMode:
    if source_scope == WEB_CUSTOM_SOURCE_SCOPE:
        return WebContentCacheMode.PRIVATE
    return WebContentCacheMode.PUBLIC


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value
