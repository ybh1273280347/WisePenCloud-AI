from __future__ import annotations

from chat.application.tools.common.web_content_cache import (
    NonHtmlCacheStubWrite,
    WebContentCacheEntryRepository,
    WebContentCacheService,
    WebContentCacheValueRepository,
    source_scope_from_metadata,
    string_metadata,
)
from chat.application.tools.utils.url import FetchedUrl
from common.logger import warn

from .models import ParsedCacheHit

_DOCUMENT_PARSE_CACHE_PARSER_VERSION = "document_parse:v1"


class DocumentParseCache:
    __slots__ = ("_content_cache_service",)

    def __init__(
            self,
            *,
            content_cache_entry_repository: WebContentCacheEntryRepository | None = None,
            content_cache_value_repository: WebContentCacheValueRepository | None = None,
    ) -> None:
        self._content_cache_service = WebContentCacheService(
            entry_repository=content_cache_entry_repository,
            value_repository=content_cache_value_repository,
        )

    async def write_direct_url_cache_stub(
            self,
            *,
            user_id: str,
            raw: FetchedUrl,
    ) -> str | None:
        return await self._content_cache_service.write_non_html_stub(
            NonHtmlCacheStubWrite(
                user_id=user_id,
                source_scope="web_public",
                source_url=raw.source_url,
                final_url=raw.final_url,
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
        final_url: str | None,
        content_type: str | None,
        cache_doc_id: str | None = None,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "source_kind": "web_fetch",
        "source_scope": "web_public",
        "source_url": url,
        "final_url": final_url,
        "content_type": content_type,
    }
    if cache_doc_id:
        metadata["source_cache_doc_id"] = cache_doc_id
    return metadata
