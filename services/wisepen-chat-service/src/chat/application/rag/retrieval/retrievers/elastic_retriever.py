from __future__ import annotations

from typing import Any

from elasticsearch import AsyncElasticsearch

from chat.application.rag.retrieval.filters import RagPermissionFilterBuilder
from chat.application.rag.retrieval.models import RagElasticStrictPrefilterRequest, RagExactFilter


class RagElasticRetriever:
    """Elasticsearch strict prefilter 检索入口。"""

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

    async def strict_prefilter(
            self,
            request: RagElasticStrictPrefilterRequest,
    ) -> tuple[str, ...]:
        if self._client is None:
            return ()

        response = await self._client.search(
            index=self._index_name,
            query=self.build_strict_prefilter_query(request),
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

    def build_strict_prefilter_query(
            self,
            request: RagElasticStrictPrefilterRequest,
    ) -> dict[str, Any]:
        exact_filter = request.exact_filter or RagExactFilter()
        filter_clauses: list[dict[str, Any]] = [
            {"term": {"resource_id": request.resource_id}},
            {"term": {"corpus_version": request.corpus_version}},
        ]
        filter_clauses.extend(_build_exact_filter_clauses(exact_filter))

        if request.permission_scope is not None:
            filter_clauses.append(
                self._permission_filter_builder.build_elastic_filter(request.permission_scope)
            )

        must_clauses = _build_phrase_clauses(request.query, exact_filter)
        bool_query: dict[str, Any] = {
            "filter": filter_clauses,
        }
        if must_clauses:
            bool_query["must"] = must_clauses
        else:
            bool_query["must"] = [{"match_all": {}}]

        return {
            "bool": bool_query,
        }


def _build_exact_filter_clauses(exact_filter: RagExactFilter) -> list[dict[str, Any]]:
    clauses: list[dict[str, Any]] = []
    if exact_filter.document_version:
        clauses.append({"term": {"document_version": exact_filter.document_version}})
    if exact_filter.chunk_ids:
        clauses.append({"terms": {"chunk_id": list(exact_filter.chunk_ids)}})
    if exact_filter.page_label:
        clauses.append({"term": {"page_label": exact_filter.page_label}})
    if exact_filter.anchor_labels:
        clauses.append({"terms": {"anchor_labels": list(exact_filter.anchor_labels)}})
    if exact_filter.section_path:
        clauses.append({"term": {"section_path_text": " > ".join(exact_filter.section_path)}})
    return clauses


def _build_phrase_clauses(query: str, exact_filter: RagExactFilter) -> list[dict[str, Any]]:
    phrases = tuple(
        phrase
        for phrase in (query, *exact_filter.required_phrases)
        if phrase.strip()
    )
    return [
        {
            "match_phrase": {
                "indexing_text": {
                    "query": phrase,
                }
            }
        }
        for phrase in phrases
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
