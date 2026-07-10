from __future__ import annotations

from dataclasses import dataclass

from chat.application.tools.common.web_content_cache import (
    NonHtmlCacheStubWrite,
    WebContentCacheRepository,
    WebContentCacheService,
)
from chat.application.tools.common.web_content_cache._utils.metadata import (
    source_scope_from_metadata,
    string_metadata,
)
from chat.application.tools.utils.url import DownloadedUrl
from common.logger import warn

_DOCUMENT_PARSE_CACHE_PARSER_VERSION = "document_parse:v1"


@dataclass(frozen=True, slots=True)
class ParsedCacheHit:
    markdown: str


class DocumentParseCache:
    __slots__ = ("_content_cache_service",)

    def __init__(
            self,
            *,
            content_cache_repository: WebContentCacheRepository | None = None,
    ) -> None:
        self._content_cache_service = WebContentCacheService(
            repository=content_cache_repository,
        )

    async def write_direct_url_cache_stub(
            self,
            *,
            user_id: str,
            raw: DownloadedUrl,
    ) -> bool:
        return await self._content_cache_service.write_non_html_stub(
            NonHtmlCacheStubWrite(
                user_id=user_id,
                source_scope="web_public",
                source_url=raw.source_url,
                status_code=raw.status_code,
                content_type=raw.content_type,
                headers=raw.headers,
                fetcher=raw.fetcher,
                file_label=raw.file_label,
            ),
        )

    async def read_parsed_web_cache(
            self,
            *,
            user_id: str,
            metadata: dict[str, object],
    ) -> ParsedCacheHit | None:
        cached = await self._content_cache_service.read_markdown_by_metadata(
            user_id=user_id,
            metadata=metadata,
            parser_version=_DOCUMENT_PARSE_CACHE_PARSER_VERSION,
        )
        if cached is None:
            return None

        return ParsedCacheHit(
            markdown=cached.markdown,
        )

    async def write_parsed_web_cache(
            self,
            *,
            user_id: str,
            metadata: dict[str, object],
            content_type: str | None,
            markdown: str,
    ) -> None:
        source_url = string_metadata(metadata, "source_url")
        source_scope = source_scope_from_metadata(metadata)
        if source_url is None or source_scope is None:
            return

        try:
            await self._content_cache_service.write_markdown_from_metadata(
                user_id=user_id,
                metadata=metadata,
                content_type=content_type,
                markdown=markdown,
                parser="document_parse",
                parser_version=_DOCUMENT_PARSE_CACHE_PARSER_VERSION,
            )
        except Exception:
            warn(
                "文档解析缓存写入失败",
                source_url=source_url,
                source_scope=source_scope,
                audit_message="文档解析结果写入网页内容缓存失败，不影响本次解析结果返回。",
            )


def direct_url_metadata(
        *,
        url: str,
        content_type: str | None,
) -> dict[str, object]:
    return {
        "source_kind": "web_fetch",
        "source_scope": "web_public",
        "source_url": url,
        "content_type": content_type,
    }
