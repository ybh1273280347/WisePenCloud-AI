from __future__ import annotations

import json
from dataclasses import asdict
from hashlib import sha256
from typing import Any

from chat.application.rag.cache import (
    RagEvidenceMaterializationCacheScope,
    RagMaterializedEvidenceView,
)
from chat.application.rag.utils import read_optional_text, read_text_tuple
from chat.core.persistence.redis._utils import to_jsonable
from chat.core.persistence.redis.base import RedisRepository

_KEY_PREFIX = "wisepen:rag:evidence_materialized:"


class RedisRagEvidenceMaterializationCache(RedisRepository):
    """Redis 短 TTL evidence 物化缓存。"""

    __slots__ = ("_ttl_seconds",)

    def __init__(self, *, redis_url: str, ttl_seconds: int) -> None:
        super().__init__(redis_url=redis_url)
        self._ttl_seconds = ttl_seconds

    async def get_many(
            self,
            *,
            scope: RagEvidenceMaterializationCacheScope,
            child_chunk_ids: tuple[str, ...],
    ) -> dict[str, RagMaterializedEvidenceView]:
        if self._ttl_seconds <= 0 or not child_chunk_ids:
            return {}

        keys = [self._key(scope=scope, child_chunk_id=chunk_id) for chunk_id in child_chunk_ids]
        values = await self._redis.mget(keys)
        result: dict[str, RagMaterializedEvidenceView] = {}
        for chunk_id, raw in zip(child_chunk_ids, values, strict=True):
            if raw is None:
                continue
            result[chunk_id] = _decode_view(json.loads(raw))
        return result

    async def set_many(
            self,
            *,
            scope: RagEvidenceMaterializationCacheScope,
            views_by_child_id: dict[str, RagMaterializedEvidenceView],
    ) -> None:
        if self._ttl_seconds <= 0 or not views_by_child_id:
            return

        async with self._redis.pipeline(transaction=True) as pipe:
            for child_chunk_id, view in views_by_child_id.items():
                await pipe.set(
                    self._key(scope=scope, child_chunk_id=child_chunk_id),
                    json.dumps(to_jsonable(asdict(view)), ensure_ascii=False),
                    ex=self._ttl_seconds,
                )
            await pipe.execute()

    @classmethod
    def _key(
            cls,
            *,
            scope: RagEvidenceMaterializationCacheScope,
            child_chunk_id: str,
    ) -> str:
        scope_hash = cls._hash(
            "\n".join(
                (
                    scope.user_id,
                    scope.session_id,
                    scope.resource_id,
                    scope.permission_scope_key,
                )
            )
        )
        return f"{_KEY_PREFIX}{scope_hash}:{cls._hash(child_chunk_id)}"

    @staticmethod
    def _hash(value: str) -> str:
        return sha256(value.encode("utf-8")).hexdigest()


def _decode_view(payload: dict[str, Any]) -> RagMaterializedEvidenceView:
    return RagMaterializedEvidenceView(
        parent_chunk_id=str(payload["parent_chunk_id"]),
        document_version=str(payload["document_version"]),
        text=str(payload["text"]),
        citation_anchor=str(payload["citation_anchor"]),
        page_label=read_optional_text(payload.get("page_label")),
        section_path=read_text_tuple(payload.get("section_path")),
        anchor_labels=read_text_tuple(payload.get("anchor_labels")),
        matched_child_ids=read_text_tuple(payload.get("matched_child_ids")),
    )
