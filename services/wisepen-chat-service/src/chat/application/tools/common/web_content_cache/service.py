from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256

from common.logger import info, warn
from ._utils.cache_ttl import compute_ttl
from ._utils.metadata import string_metadata
from .core.models import (
    WebContentCacheMode,
    WebContentCacheValue,
)
from .core.protocols import WebContentCacheRepository

WEB_PUBLIC_SOURCE_SCOPE = "web_public"
WEB_CUSTOM_SOURCE_SCOPE = "web_custom"


@dataclass(frozen=True, slots=True)
class CachedMarkdownPage:
    """URL 缓存命中的 HTML/Markdown 页面。"""

    source_url: str
    status_code: int | None
    content_type: str | None
    title: str | None
    markdown: str
    raw_html: str | None
    cache_mode: WebContentCacheMode


@dataclass(frozen=True, slots=True)
class HtmlCacheWrite:
    """写入 URL HTML 缓存所需的最小数据。"""

    url: str
    user_id: str
    source_scope: str
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
    status_code: int | None
    content_type: str | None
    headers: dict[str, str]
    fetcher: str | None
    file_label: str | None
    source_kind: str = "web_fetch"
    extra_metadata: dict[str, object] | None = None


class WebContentCacheService:
    """URL 内容缓存门面，封装 Redis 读写。"""

    __slots__ = ("_repository",)

    def __init__(
            self,
            *,
            repository: WebContentCacheRepository | None,
    ) -> None:
        self._repository = repository

    async def read_markdown_page(
            self,
            *,
            url: str,
            user_id: str,
    ) -> CachedMarkdownPage | None:
        """读取 URL markdown 缓存。"""
        repository = self._repository
        if repository is None:
            return None

        try:
            now = datetime.now(timezone.utc)
            for mode in (WebContentCacheMode.PRIVATE, WebContentCacheMode.PUBLIC):
                value = await repository.get_value(
                    user_id=user_id,
                    url=url,
                    cache_mode=mode,
                )
                cached = _cached_markdown_page(value=value, source_url=url, now=now)
                if cached is None:
                    continue

                info(
                    "URL markdown 缓存命中",
                    url=url,
                    cache_mode=value.cache_mode.value,
                )
                return cached
        except Exception as exc:
            warn("URL markdown 缓存读取失败，降级为实时获取", url=url, e=exc)

        return None

    async def write_html_markdown(self, write: HtmlCacheWrite) -> bool:
        """写入 HTML 清洗结果缓存；失败返回 False，不影响调用方结果。"""
        repository = self._repository
        if repository is None or not write.markdown:
            return False

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
                return False

            canonical_url = write.url.strip()
            content_hash_payload = f"{write.raw_html or ''}\n---markdown---\n{write.markdown}"
            await repository.set_value(
                WebContentCacheValue(
                    user_id=write.user_id,
                    canonical_url=canonical_url,
                    cache_mode=mode,
                    status_code=write.status_code,
                    content_type=write.content_type,
                    raw_html=write.raw_html,
                    markdown=write.markdown,
                    content_hash=sha256(content_hash_payload.encode("utf-8")).hexdigest(),
                    fetched_at=now,
                    expire_at=ttl.expire_at,
                    etag=write.headers.get("etag"),
                    last_modified=write.headers.get("last-modified"),
                    metadata={
                        "title": write.title,
                        "source_scope": write.source_scope,
                        "source_url": write.url,
                        "fetcher": write.fetcher,
                        "cleaner": write.cleaner,
                        "producer": write.producer,
                        "cache_control": write.headers.get("cache-control"),
                        **(write.extra_metadata or {}),
                    },
                )
            )
            info(
                "URL HTML 缓存已写入",
                url=write.url,
                cache_mode=mode.value,
                producer=write.producer,
            )
            return True
        except Exception as exc:
            warn("URL HTML 缓存写入失败", url=write.url, e=exc)
            return False

    async def write_non_html_stub(self, write: NonHtmlCacheStubWrite) -> bool:
        """为非 HTML 文件预创建 URL 缓存记录，供后续 parser 回写 markdown。"""
        repository = self._repository
        if repository is None:
            return False

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
                return False

            await repository.set_value(
                WebContentCacheValue(
                    user_id=write.user_id,
                    canonical_url=write.source_url.strip(),
                    cache_mode=mode,
                    status_code=write.status_code,
                    content_type=write.content_type,
                    raw_html=None,
                    markdown=None,
                    fetched_at=now,
                    expire_at=ttl.expire_at,
                    etag=write.headers.get("etag"),
                    last_modified=write.headers.get("last-modified"),
                    metadata={
                        "source_kind": write.source_kind,
                        "source_scope": write.source_scope,
                        "source_url": write.source_url,
                        "fetcher": write.fetcher,
                        "file_label": write.file_label,
                        "cache_control": write.headers.get("cache-control"),
                        **(write.extra_metadata or {}),
                    },
                )
            )
            info("URL 非 HTML 缓存占位已写入", url=write.source_url, cache_mode=mode.value)
            return True
        except Exception as exc:
            warn("URL 非 HTML 缓存占位写入失败", url=write.source_url, e=exc)
            return False

    async def read_markdown_by_metadata(
            self,
            *,
            user_id: str,
            metadata: dict[str, object],
            parser_version: str | None = None,
    ) -> CachedMarkdownPage | None:
        """按 metadata 中的 URL/source_scope 精确读取 markdown 缓存，不做 public/private 回退。"""
        repository = self._repository
        if repository is None:
            return None

        source_kind = string_metadata(metadata, "source_kind")
        source_scope = string_metadata(metadata, "source_scope")
        source_url = string_metadata(metadata, "source_url")
        if source_kind != "web_fetch" or source_scope is None or source_url is None:
            return None

        try:
            value = await repository.get_value(
                user_id=user_id,
                url=source_url,
                cache_mode=_cache_mode_for_source_scope(source_scope),
            )
            if (
                    value is not None
                    and parser_version is not None
                    and value.metadata.get("parser_version") != parser_version
            ):
                return None

            return _cached_markdown_page(
                value=value,
                source_url=source_url,
                now=datetime.now(timezone.utc),
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
    ) -> bool:
        """按 URL/source_scope 回写非 HTML parser 结果。"""
        repository = self._repository
        if repository is None or not markdown:
            return False

        source_kind = string_metadata(metadata, "source_kind")
        source_scope = string_metadata(metadata, "source_scope")
        source_url = string_metadata(metadata, "source_url")
        if source_kind != "web_fetch" or source_scope is None or source_url is None:
            return False

        try:
            now = datetime.now(timezone.utc)
            mode = _cache_mode_for_source_scope(source_scope)
            existing = await repository.get_value(
                user_id=user_id,
                url=source_url,
                cache_mode=mode,
            )
            cache_control_header = (
                existing.metadata.get("cache_control")
                if existing is not None and isinstance(existing.metadata, dict)
                else None
            )
            ttl = compute_ttl(
                headers={"cache-control": cache_control_header} if isinstance(cache_control_header, str) else {},
                now=now,
                is_shared_cache=(mode == WebContentCacheMode.PUBLIC),
                status_code=existing.status_code if existing is not None else 200,
            )
            if ttl.no_store:
                return False

            raw_html = existing.raw_html if existing is not None else None
            content_hash_payload = f"{raw_html or ''}\n---markdown---\n{markdown}"
            value = WebContentCacheValue(
                user_id=user_id,
                canonical_url=existing.canonical_url if existing is not None else source_url.strip(),
                cache_mode=mode,
                status_code=existing.status_code if existing is not None else None,
                content_type=existing.content_type if existing is not None else content_type,
                raw_html=raw_html,
                markdown=markdown,
                content_hash=sha256(content_hash_payload.encode("utf-8")).hexdigest(),
                fetched_at=existing.fetched_at if existing is not None else now,
                expire_at=ttl.expire_at,
                etag=existing.etag if existing is not None else None,
                last_modified=existing.last_modified if existing is not None else None,
                metadata={
                    **(existing.metadata if existing is not None else {}),
                    "source_kind": source_kind,
                    "source_scope": source_scope,
                    "source_url": source_url,
                    "content_type": content_type,
                    "parser": parser,
                    "parser_version": parser_version,
                },
            )
            await repository.set_value(value)
            info("URL parser markdown 已回写缓存", source_url=source_url, cache_mode=mode.value)
            return True
        except Exception as exc:
            warn("URL parser markdown 回写缓存失败", source_url=source_url, e=exc)
            return False


def _cached_markdown_page(
        *,
        value: WebContentCacheValue | None,
        source_url: str,
        now: datetime,
) -> CachedMarkdownPage | None:
    if value is None or not value.markdown:
        return None

    expire_at = value.expire_at
    if expire_at is not None and now > _ensure_aware(expire_at):
        return None

    title = value.metadata.get("title")
    return CachedMarkdownPage(
        source_url=source_url,
        status_code=value.status_code,
        content_type=value.content_type,
        title=title if isinstance(title, str) else None,
        markdown=value.markdown,
        raw_html=value.raw_html,
        cache_mode=value.cache_mode,
    )


def _cache_mode_for_source_scope(source_scope: str) -> WebContentCacheMode:
    if source_scope == WEB_CUSTOM_SOURCE_SCOPE:
        return WebContentCacheMode.PRIVATE
    return WebContentCacheMode.PUBLIC


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value
