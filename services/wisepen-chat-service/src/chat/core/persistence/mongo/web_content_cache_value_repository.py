from __future__ import annotations

from datetime import datetime, timezone

from beanie import PydanticObjectId

from chat.application.tools.common.web_content_cache.core.models import (
    WebContentCacheValue,
)
from chat.domain.entities.web_content_cache import WebContentCacheValueDocument


class MongoWebContentCacheValueRepository:
    """MongoDB 侧：URL 缓存正文内容存储。"""

    async def get_value(self, *, doc_id: str) -> WebContentCacheValue | None:
        document = await WebContentCacheValueDocument.get(PydanticObjectId(doc_id))
        if document is None:
            return None

        return WebContentCacheValue(
            id=str(document.id) if document.id is not None else None,
            user_id=document.user_id,
            canonical_url=document.canonical_url,
            final_url=document.final_url,
            cache_mode=document.cache_mode,
            status_code=document.status_code,
            content_type=document.content_type,
            raw_html=document.raw_html,
            markdown=document.markdown,
            content_hash=document.content_hash,
            fetched_at=document.fetched_at,
            metadata=document.metadata,
        )

    async def save_value(self, value: WebContentCacheValue) -> str:
        now = datetime.now(timezone.utc)

        if value.id:
            document = await WebContentCacheValueDocument.get(PydanticObjectId(value.id))
            if document is not None:
                document.canonical_url = value.canonical_url
                document.user_id = value.user_id
                document.final_url = value.final_url
                document.cache_mode = value.cache_mode
                document.status_code = value.status_code
                document.content_type = value.content_type
                document.raw_html = value.raw_html
                document.markdown = value.markdown
                document.content_hash = value.content_hash
                document.fetched_at = value.fetched_at
                document.metadata = value.metadata
                document.updated_at = now
                await document.save()
                return str(document.id)

        document = WebContentCacheValueDocument(
            user_id=value.user_id,
            canonical_url=value.canonical_url,
            final_url=value.final_url,
            cache_mode=value.cache_mode,
            status_code=value.status_code,
            content_type=value.content_type,
            raw_html=value.raw_html,
            markdown=value.markdown,
            content_hash=value.content_hash,
            fetched_at=value.fetched_at,
            metadata=value.metadata,
            created_at=now,
            updated_at=now,
        )
        await document.insert()
        return str(document.id)
