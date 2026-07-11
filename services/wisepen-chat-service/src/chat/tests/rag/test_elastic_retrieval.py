from __future__ import annotations

from typing import Any

import pytest

from chat.application.rag.retrieval.models import (
    RagElasticKeywordFilterRequest,
    RagPermissionScope,
)
from chat.application.rag.retrieval.permission_filter import RagPermissionFilterBuilder
from chat.application.rag.retrieval.pipeline.elastic_filter import RagElasticFilter


def test_elastic_keyword_filter_builds_content_phrase_query_with_scope_filters() -> None:
    elastic_filter = RagElasticFilter(
        client=_FakeElasticClient(),
        index_name="rag-test",
        permission_filter_builder=RagPermissionFilterBuilder(),
    )

    query = elastic_filter.build_keyword_filter_query(
        RagElasticKeywordFilterRequest(
            keywords=("AppBuilder API Key", "Bearer token"),
            resource_id="res-1",
            permission_scope=RagPermissionScope(
                user_id="user-1",
                group_role_map={
                    "group-admin": "ADMIN",
                    "group-member": "MEMBER",
                },
            ),
            limit=20,
        )
    )

    bool_query = query["bool"]
    assert {"term": {"resource_id": "res-1"}} in bool_query["filter"]
    assert bool_query["must"] == [
        {"match_phrase": {"indexing_text": {"query": "AppBuilder API Key"}}},
        {"match_phrase": {"indexing_text": {"query": "Bearer token"}}},
    ]
    assert bool_query["filter"][-1]["bool"]["minimum_should_match"] == 1


def test_permission_filter_keeps_group_acl_exceptions_nested() -> None:
    query = RagPermissionFilterBuilder().build_elastic_filter(
        RagPermissionScope(
            user_id="user-1",
            group_role_map={
                "managed": "OWNER",
                "joined": "MEMBER",
            },
        )
    )

    should = query["bool"]["should"]
    assert {"term": {"owner_id": "user-1"}} in should
    assert {"term": {"readable_users": "user-1"}} in should
    assert any(item.get("nested", {}).get("path") == "computed_group_acls" for item in should)

    member_discover = should[3]["nested"]["query"]["bool"]
    assert {"terms": {"computed_group_acls.group_id": ["managed", "joined"]}} in member_discover["filter"]
    assert {"term": {"computed_group_acls.is_readable": True}} in member_discover["filter"]
    assert member_discover["must_not"] == [
        {"term": {"computed_group_acls.excluded_read_users": "user-1"}}
    ]


@pytest.mark.anyio
async def test_elastic_strict_prefilter_returns_chunk_ids_from_source() -> None:
    client = _FakeElasticClient(
        response={
            "hits": {
                "hits": [
                    {"_source": {"chunk_id": "chunk-a"}},
                    {"_source": {"chunk_id": "chunk-b"}},
                    {"_source": {}},
                ]
            }
        }
    )
    elastic_filter = RagElasticFilter(
        client=client,
        index_name="rag-test",
        permission_filter_builder=RagPermissionFilterBuilder(),
    )

    chunk_ids = await elastic_filter.filter_candidate_chunk_ids(
        RagElasticKeywordFilterRequest(
            keywords=("API Key",),
            resource_id="res-1",
        )
    )

    assert chunk_ids == ("chunk-a", "chunk-b")
    assert client.search_calls[0]["index"] == "rag-test"
    assert client.search_calls[0]["size"] == 1000
    assert client.search_calls[0]["source_includes"] == ["chunk_id"]


class _FakeElasticClient:
    def __init__(self, *, response: dict[str, Any] | None = None) -> None:
        self.response = response or {"hits": {"hits": []}}
        self.search_calls: list[dict[str, Any]] = []
        self.delete_by_query_calls: list[dict[str, Any]] = []

    async def search(self, **kwargs: Any) -> dict[str, Any]:
        self.search_calls.append(kwargs)
        return self.response

    async def delete_by_query(self, **kwargs: Any) -> None:
        self.delete_by_query_calls.append(kwargs)
