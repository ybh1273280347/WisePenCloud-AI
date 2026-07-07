from __future__ import annotations

import json
from dataclasses import asdict
from hashlib import sha256
from typing import Any

from chat.application.rag.utils import read_optional_text, read_text_tuple
from chat.application.rag.cache.graph_enhancement import RagGraphEnhancementCacheKey
from chat.application.rag.graph import (
    RagConceptPath,
    RagGraphEnhancementResult,
    RagGraphEvidence,
    RagOntologyHint,
)
from chat.core.persistence.redis._utils import to_jsonable
from chat.core.persistence.redis.base import RedisRepository

_KEY_PREFIX = "wisepen:rag:graph_enhancement:"


class RedisRagGraphEnhancementCache(RedisRepository):
    """Redis 侧 Neo4j graph enhancement 结果缓存。"""

    __slots__ = ("_ttl_seconds",)

    def __init__(self, *, redis_url: str, ttl_seconds: int) -> None:
        super().__init__(redis_url=redis_url)
        self._ttl_seconds = ttl_seconds

    async def get_graph_enhancement(
            self,
            key: RagGraphEnhancementCacheKey,
    ) -> RagGraphEnhancementResult | None:
        if self._ttl_seconds <= 0:
            return None

        raw = await self._redis.get(self._key(key))
        if raw is None:
            return None
        return _decode_result(json.loads(raw))

    async def set_graph_enhancement(
            self,
            key: RagGraphEnhancementCacheKey,
            result: RagGraphEnhancementResult,
    ) -> None:
        if self._ttl_seconds <= 0:
            return

        await self._redis.set(
            self._key(key),
            json.dumps(to_jsonable(asdict(result)), ensure_ascii=False),
            ex=self._ttl_seconds,
        )

    @classmethod
    def _key(cls, key: RagGraphEnhancementCacheKey) -> str:
        payload = json.dumps(to_jsonable(asdict(key)), ensure_ascii=False, sort_keys=True)
        return f"{_KEY_PREFIX}{sha256(payload.encode('utf-8')).hexdigest()}"


def _decode_result(payload: dict[str, Any]) -> RagGraphEnhancementResult:
    return RagGraphEnhancementResult(
        graph_evidence=tuple(
            _decode_graph_evidence(item)
            for item in payload.get("graph_evidence", [])
            if isinstance(item, dict)
        ),
        ontology_hints=tuple(
            _decode_hint(item)
            for item in payload.get("ontology_hints", [])
            if isinstance(item, dict)
        ),
        concept_paths=tuple(
            _decode_path(item)
            for item in payload.get("concept_paths", [])
            if isinstance(item, dict)
        ),
    )


def _decode_graph_evidence(payload: dict[str, Any]) -> RagGraphEvidence:
    return RagGraphEvidence(
        chunk_id=str(payload["chunk_id"]),
        document_version=str(payload["document_version"]),
        evidence_text=str(payload["evidence_text"]),
        page_label=read_optional_text(payload.get("page_label")),
        section_path=read_text_tuple(payload.get("section_path")),
        anchor_labels=read_text_tuple(payload.get("anchor_labels")),
        path=read_text_tuple(payload.get("path")),
        related_concepts=read_text_tuple(payload.get("related_concepts")),
    )


def _decode_hint(payload: dict[str, Any]) -> RagOntologyHint:
    return RagOntologyHint(
        concept=str(payload["concept"]),
        class_candidates=read_text_tuple(payload.get("class_candidates")),
        relation_type_candidates=read_text_tuple(payload.get("relation_type_candidates")),
        path_preview=read_text_tuple(payload.get("path_preview")),
    )


def _decode_path(payload: dict[str, Any]) -> RagConceptPath:
    return RagConceptPath(
        source_concept=str(payload["source_concept"]),
        target_concept=str(payload["target_concept"]),
        path=read_text_tuple(payload.get("path")),
        support_chunk_ids=read_text_tuple(payload.get("support_chunk_ids")),
    )
