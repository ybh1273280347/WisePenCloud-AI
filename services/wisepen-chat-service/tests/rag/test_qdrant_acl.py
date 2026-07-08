from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from chat.application.rag.acl import (  # noqa: E402
    RagComputedGroupAclProjection,
    RagResourceAclProjection,
)
from chat.application.rag.retrieval.models import (  # noqa: E402
    RagPermissionScope,
    RagQdrantRetrievalFilterRequest,
    RagQdrantRetrievalRequest,
    RagRetrievalChannel,
)
from chat.application.rag.retrieval.permission_filter import RagPermissionFilterBuilder  # noqa: E402
from chat.application.rag.retrieval.pipeline.qdrant_retrieve import RagQdrantRetriever  # noqa: E402
from chat.core.persistence.qdrant import RagQdrantRepository  # noqa: E402
from qdrant_client import models as qdrant_models  # noqa: E402
from qdrant_client.conversions import common_types as qdrant_types  # noqa: E402


def test_qdrant_permission_filter_keeps_group_acl_exceptions_nested() -> None:
    query = RagPermissionFilterBuilder().build_qdrant_filter(
        RagPermissionScope(
            user_id="user-1",
            group_role_map={
                "managed": "OWNER",
                "joined": "MEMBER",
            },
        )
    )

    assert query.should is not None
    assert len(query.should) == 5
    nested = query.should[3].nested
    assert nested is not None
    assert nested.key == "computed_group_acls"
    assert [condition.key for condition in nested.filter.must] == ["group_id", "is_readable"]
    assert nested.filter.must_not[0].key == "excluded_read_users"


def test_neo4j_permission_predicate_matches_read_acl_scope() -> None:
    predicate, params = RagPermissionFilterBuilder().build_neo4j_predicate(
        RagPermissionScope(
            user_id="user-1",
            group_role_map={
                "managed": "OWNER",
                "joined": "MEMBER",
            },
        ),
        node_alias="candidate",
    )

    assert "candidate.owner_id = $rag_acl_user_id" in predicate
    assert "candidate.readable_users" in predicate
    assert "candidate.computed_group_acls" in predicate
    assert "excluded_read_users" in predicate
    assert params == {
        "rag_acl_user_id": "user-1",
        "rag_acl_managed_group_ids": ["managed"],
        "rag_acl_joined_group_ids": ["managed", "joined"],
    }


def test_qdrant_retrieval_filter_appends_permission_scope() -> None:
    retriever = RagQdrantRetriever(
        client=_FakeQdrantClient(),
        collection_name="rag-test",
        permission_filter_builder=RagPermissionFilterBuilder(),
        bm25_config=_bm25_config(),
    )

    query = retriever.build_retrieval_filter(
        RagQdrantRetrievalFilterRequest(
            resource_id="res-1",
            candidate_chunk_ids=("chunk-a", "chunk-b"),
            permission_scope=RagPermissionScope(
                user_id="user-1",
                group_role_map={"group-1": "MEMBER"},
            ),
        )
    )

    assert query.must is not None
    assert [condition.key for condition in query.must[:2]] == [
        "resource_id",
        "chunk_id",
    ]
    assert query.must[2].should is not None


@pytest.mark.anyio
async def test_qdrant_acl_projection_updates_payload_by_resource_filter() -> None:
    client = _FakeQdrantClient()
    repository = RagQdrantRepository(
        client=client,
        collection_name="rag-test",
        dense_vector_size=2,
        bm25_config=_bm25_config(),
    )

    await repository.update_acl_projection(
        RagResourceAclProjection(
            resource_id="res-1",
            owner_id="owner-1",
            readable_users=("user-a",),
            computed_group_acls=(
                RagComputedGroupAclProjection(
                    group_id="group-1",
                    is_readable=True,
                    excluded_read_users=("blocked",),
                ),
            ),
        )
    )

    call = client.set_payload_calls[0]
    assert call["collection_name"] == "rag-test"
    assert call["payload"] == {
        "owner_id": "owner-1",
        "readable_users": ["user-a"],
        "computed_group_acls": [
            {
                "group_id": "group-1",
                "is_readable": True,
                "readable_users": [],
                "excluded_read_users": ["blocked"],
            }
        ],
    }
    assert call["points"].must[0].key == "resource_id"


@pytest.mark.anyio
async def test_qdrant_retrieve_queries_dense_and_sparse_channels() -> None:
    client = _FakeQdrantClient()
    payload = {
        "chunk_id": "chunk-a",
        "parent_chunk_id": "parent-a",
        "resource_id": "res-1",
        "document_version": "3",
        "corpus_version": "3",
        "evidence_text": "AppBuilder API Key 用于鉴权。",
        "page_label": "1",
        "section_path": ["鉴权"],
        "anchor_labels": ["表 1"],
    }
    client.query_responses = [
        qdrant_types.QueryResponse(
            points=[
                _scored_point("chunk-a", score=0.82, payload=payload),
            ]
        ),
        qdrant_types.QueryResponse(
            points=[
                _scored_point("chunk-a", score=0.77, payload=payload),
            ]
        ),
    ]
    retriever = RagQdrantRetriever(
        client=client,
        collection_name="rag-test",
        permission_filter_builder=RagPermissionFilterBuilder(),
        bm25_config=_bm25_config(),
    )

    chunks = await retriever.retrieve(
        RagQdrantRetrievalRequest(
            resource_id="res-1",
            query_text="AppBuilder API Key",
            query_vector=[0.1, 0.2],
            candidate_chunk_ids=("chunk-a",),
            top_k=10,
        )
    )

    dense_call, sparse_call = client.query_points_calls
    assert dense_call["collection_name"] == "rag-test"
    assert [call["using"] for call in client.query_points_calls] == ["dense", "sparse"]
    assert all("prefetch" not in call for call in client.query_points_calls)
    sparse_query = sparse_call["query"]
    assert isinstance(sparse_query, qdrant_models.Document)
    assert sparse_query.model == "Qdrant/bm25"
    assert sparse_query.text == "AppBuilder API Key"
    assert chunks[0].chunk_id == "chunk-a"
    assert chunks[0].retrieval_channels == (
        RagRetrievalChannel.DENSE,
        RagRetrievalChannel.SPARSE,
    )
    assert [(signal.channel, signal.rank) for signal in chunks[0].retrieval_signals] == [
        (RagRetrievalChannel.DENSE, 1),
        (RagRetrievalChannel.SPARSE, 1),
    ]


@pytest.mark.anyio
async def test_qdrant_retrieve_returns_dense_sparse_channel_signals() -> None:
    client = _FakeQdrantClient()
    client.query_responses = [
        qdrant_types.QueryResponse(
            points=[
                _scored_point("dense-a", score=0.91),
                _scored_point("shared", score=0.88),
            ]
        ),
        qdrant_types.QueryResponse(
            points=[
                _scored_point("sparse-a", score=0.93),
                _scored_point("shared", score=0.87),
            ]
        ),
    ]
    retriever = RagQdrantRetriever(
        client=client,
        collection_name="rag-test",
        permission_filter_builder=RagPermissionFilterBuilder(),
        bm25_config=_bm25_config(),
    )

    chunks = await retriever.retrieve(
        RagQdrantRetrievalRequest(
            resource_id="res-1",
            query_text="概念性问题",
            query_vector=[0.1, 0.2],
            top_k=10,
        )
    )

    assert [call["using"] for call in client.query_points_calls] == ["dense", "sparse"]
    assert all("prefetch" not in call for call in client.query_points_calls)
    assert [chunk.chunk_id for chunk in chunks] == ["dense-a", "shared", "sparse-a"]
    assert chunks[0].retrieval_channels == (RagRetrievalChannel.DENSE,)
    assert chunks[1].retrieval_channels == (
        RagRetrievalChannel.DENSE,
        RagRetrievalChannel.SPARSE,
    )
    assert [(signal.channel, signal.rank) for signal in chunks[1].retrieval_signals] == [
        (RagRetrievalChannel.DENSE, 2),
        (RagRetrievalChannel.SPARSE, 2),
    ]


@pytest.mark.anyio
async def test_qdrant_retrieve_uses_dense_only_when_query_text_is_empty() -> None:
    client = _FakeQdrantClient()
    client.query_response = qdrant_types.QueryResponse(
        points=[
            _scored_point("dense-a", score=0.91),
        ]
    )
    retriever = RagQdrantRetriever(
        client=client,
        collection_name="rag-test",
        permission_filter_builder=RagPermissionFilterBuilder(),
        bm25_config=_bm25_config(),
    )

    chunks = await retriever.retrieve(
        RagQdrantRetrievalRequest(
            resource_id="res-1",
            query_text="",
            query_vector=[0.1, 0.2],
            top_k=10,
        )
    )

    assert [call["using"] for call in client.query_points_calls] == ["dense"]
    assert chunks[0].retrieval_channels == (RagRetrievalChannel.DENSE,)


@pytest.mark.anyio
async def test_qdrant_upsert_uses_native_bm25_document_for_sparse_vector() -> None:
    client = _FakeQdrantClient()
    repository = RagQdrantRepository(
        client=client,
        collection_name="rag-test",
        dense_vector_size=2,
        bm25_config=_bm25_config(),
    )

    await repository.upsert_child_chunks(
        child_chunks=(_ChildChunk(),),
        dense_vectors={"chunk-a": [0.1, 0.2]},
        resource_id="res-1",
        document_version="3",
        corpus_version="3",
    )

    point = client.upsert_calls[0]["points"][0]
    vector = point.vector
    sparse_document = vector["sparse"]
    assert vector["dense"] == [0.1, 0.2]
    assert isinstance(sparse_document, qdrant_models.Document)
    assert sparse_document.model == "Qdrant/bm25"
    assert sparse_document.text == "用于 BM25 的索引文本。"
    assert sparse_document.options.tokenizer == qdrant_models.TokenizerType.MULTILINGUAL


def _bm25_config() -> qdrant_models.Bm25Config:
    return qdrant_models.Bm25Config(
        tokenizer=qdrant_models.TokenizerType.MULTILINGUAL,
    )


class _FakeQdrantClient:
    def __init__(self) -> None:
        self.set_payload_calls: list[dict[str, Any]] = []
        self.upsert_calls: list[dict[str, Any]] = []
        self.delete_calls: list[dict[str, Any]] = []
        self.collection_exists_calls: list[str] = []
        self.create_collection_calls: list[dict[str, Any]] = []
        self.update_collection_calls: list[dict[str, Any]] = []
        self.query_points_calls: list[dict[str, Any]] = []
        self.query_responses: list[Any] = []
        self.query_response: qdrant_types.QueryResponse = qdrant_types.QueryResponse(points=[])

    async def set_payload(self, **kwargs: Any) -> None:
        self.set_payload_calls.append(kwargs)

    async def upsert(self, **kwargs: Any) -> None:
        self.upsert_calls.append(kwargs)

    async def delete(self, **kwargs: Any) -> None:
        self.delete_calls.append(kwargs)

    async def collection_exists(self, collection_name: str) -> bool:
        self.collection_exists_calls.append(collection_name)
        return False

    async def create_collection(self, **kwargs: Any) -> None:
        self.create_collection_calls.append(kwargs)

    async def update_collection(self, **kwargs: Any) -> None:
        self.update_collection_calls.append(kwargs)

    async def query_points(self, **kwargs: Any) -> Any:
        self.query_points_calls.append(kwargs)
        if self.query_responses:
            return self.query_responses.pop(0)
        return self.query_response


def _scored_point(
        chunk_id: str,
        *,
        score: float,
        payload: dict[str, Any] | None = None,
) -> qdrant_types.ScoredPoint:
    return qdrant_types.ScoredPoint(
        id=chunk_id,
        version=1,
        score=score,
        payload=payload or _payload(chunk_id),
    )


def _payload(chunk_id: str) -> dict[str, Any]:
    return {
        "chunk_id": chunk_id,
        "parent_chunk_id": f"parent-{chunk_id}",
        "resource_id": "res-1",
        "document_version": "3",
        "corpus_version": "3",
        "evidence_text": f"{chunk_id} evidence",
    }


class _ChildChunk:
    chunk_id = "chunk-a"
    parent_chunk_id = "parent-a"
    content_hash = "hash-a"
    text = "原始证据文本。"
    indexing_text = "用于 BM25 的索引文本。"
    page_label = "1"
    section_path = ("鉴权",)
    anchor_labels = ()
    start_offset = 0
    end_offset = 8
