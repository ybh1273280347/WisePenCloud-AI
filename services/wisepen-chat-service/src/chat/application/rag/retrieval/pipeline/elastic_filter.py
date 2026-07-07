from __future__ import annotations

from typing import Any

from elasticsearch import AsyncElasticsearch

from chat.application.rag.retrieval.models import RagElasticKeywordFilterRequest
from chat.application.rag.retrieval.permission_filter import RagPermissionFilterBuilder


class RagElasticFilter:
    """Elasticsearch chunk 内容关键词 prefilter 步骤。

    Elastic 只根据 indexing_text 做严格词面过滤；resource/ACL 条件只是范围约束，
    不作为内容事实来源。
    """

    __slots__ = ("_client", "_index_name", "_permission_filter_builder")

    def __init__(
            self,
            *,
            client: AsyncElasticsearch | None,
            index_name: str,
            permission_filter_builder: RagPermissionFilterBuilder,
    ) -> None:
        self._client = client
        self._index_name = index_name
        self._permission_filter_builder = permission_filter_builder

    async def filter_candidate_chunk_ids(
            self,
            request: RagElasticKeywordFilterRequest,
    ) -> tuple[str, ...]:
        if self._client is None or not request.keywords:
            return ()

        response = await self._client.search(
            index=self._index_name,
            query=self.build_keyword_filter_query(request),
            size=request.limit,
            source_includes=["chunk_id"],
            track_total_hits=False,
        )
        hits = response.get("hits", {}).get("hits", ())
        return tuple(
            chunk_id
            for hit in hits
            if (chunk_id := _read_hit_chunk_id(hit))
        )

    def build_keyword_filter_query(
            self,
            request: RagElasticKeywordFilterRequest,
    ) -> dict[str, Any]:
        filter_clauses: list[dict[str, Any]] = [
            {"term": {"resource_id": request.resource_id}},
        ]

        if request.permission_scope is not None:
            filter_clauses.append(
                self._permission_filter_builder.build_elastic_filter(request.permission_scope)
            )

        return {
            "bool": {
                "filter": filter_clauses,
                "must": _build_phrase_clauses(request.keywords),
            },
        }


def _build_phrase_clauses(phrases: tuple[str, ...]) -> list[dict[str, Any]]:
    # keywords 为空时调用方会跳过 Elastic；这里不构造 match_all，避免误放大候选范围。
    return [
        {
            "match_phrase": {
                "indexing_text": {
                    "query": phrase.strip(),
                }
            }
        }
        for phrase in phrases
        if phrase.strip()
    ]


def _read_hit_chunk_id(hit: Any) -> str | None:
    if not isinstance(hit, dict):
        return None
    source = hit.get("_source")
    if not isinstance(source, dict):
        return None
    value = source.get("chunk_id")
    if value is None:
        return None
    text = str(value).strip()
    return text or None
