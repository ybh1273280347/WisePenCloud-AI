from __future__ import annotations

from typing import Any

from elasticsearch import AsyncElasticsearch

from chat.application.rag.retrieval.models import RagElasticKeywordFilterRequest
from chat.application.rag.retrieval.permission_filter import RagPermissionFilterBuilder


class RagElasticFilter:
    """用 indexing_text 做严格词面预过滤，resource 和 ACL 仅约束检索范围。"""

    __slots__ = ("_client", "_index_name", "_permission_filter_builder")

    def __init__(
        self,
        *,
        client: AsyncElasticsearch | None,
        index_name: str,
        permission_filter_builder: RagPermissionFilterBuilder,
    ) -> None:
        index_name = index_name.strip()
        if not index_name:
            raise ValueError("index_name must not be empty.")

        self._client = client
        self._index_name = index_name
        self._permission_filter_builder = permission_filter_builder

    async def filter_candidate_chunk_ids(
        self,
        request: RagElasticKeywordFilterRequest,
    ) -> tuple[str, ...]:
        client = self._client
        if (
            client is None
            or request.limit <= 0
            or not any(keyword.strip() for keyword in request.keywords)
        ):
            return ()

        response = await client.search(
            index=self._index_name,
            query=self.build_keyword_filter_query(request),
            size=request.limit,
            source_includes=["chunk_id"],
            track_total_hits=False,
        )

        chunk_ids: list[str] = []
        seen: set[str] = set()
        for hit in response.get("hits", {}).get("hits", ()):
            if not isinstance(hit, dict):
                continue

            source = hit.get("_source")
            if not isinstance(source, dict):
                continue

            value = source.get("chunk_id")
            chunk_id = str(value).strip() if value is not None else ""
            if chunk_id and chunk_id not in seen:
                seen.add(chunk_id)
                chunk_ids.append(chunk_id)

        return tuple(chunk_ids)

    def build_keyword_filter_query(
        self,
        request: RagElasticKeywordFilterRequest,
    ) -> dict[str, Any]:
        """构造 resource/ACL 范围内所有关键词均需命中的短语查询。"""
        keywords = tuple(dict.fromkeys(
            keyword.strip()
            for keyword in request.keywords
            if keyword.strip()
        ))
        if not keywords:
            # 防止外部直接调用本方法时退化成仅按 resource/ACL 扫描。
            return {"match_none": {}}

        filters: list[dict[str, Any]] = [
            {"term": {"resource_id": request.resource_id}},
        ]
        if request.permission_scope is not None:
            filters.append(
                self._permission_filter_builder.build_elastic_filter(
                    request.permission_scope
                )
            )

        return {
            "bool": {
                "filter": filters,
                "must": [
                    {
                        "match_phrase": {
                            "indexing_text": {
                                "query": keyword,
                            }
                        }
                    }
                    for keyword in keywords
                ],
            }
        }