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
from chat.application.rag.retrieval import (  # noqa: E402
    RagPermissionFilterBuilder,
    RagPermissionScope,
    RagQdrantRetrievalFilterRequest,
    RagQdrantRetrievalRequest,
    RagQdrantRetriever,
    RagRetrievalChannel,
)
from chat.core.persistence.qdrant import RagQdrantRepository  # noqa: E402
from qdrant_client import models as qdrant_models  # noqa: E402


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
            corpus_version="corpus-1",
            candidate_chunk_ids=("chunk-a", "chunk-b"),
            permission_scope=RagPermissionScope(
                user_id="user-1",
                group_role_map={"group-1": "MEMBER"},
            ),
        )
    )

    assert query.must is not None
    assert [condition.key for condition in query.must[:3]] == [
        "resource_id",
        "corpus_version",
        "chunk_id",
    ]
    assert query.must[3].should is not None


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
async def test_qdrant_retrieve_uses_dense_sparse_rrf_prefetch() -> None:
    client = _FakeQdrantClient()
    client.query_response = _QueryResponse(
        [
            _ScoredPoint(
                score=0.82,
                payload={
                    "chunk_id": "chunk-a",
                    "parent_chunk_id": "parent-a",
                    "resource_id": "res-1",
                    "document_version": "3",
                    "corpus_version": "3",
                    "evidence_text": "AppBuilder API Key 用于鉴权。",
                    "page_label": "1",
                    "section_path": ["鉴权"],
                    "anchor_labels": ["表 1"],
                },
            )
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
            corpus_version="3",
            query_text="AppBuilder API Key",
            query_vector=[0.1, 0.2],
            candidate_chunk_ids=("chunk-a",),
            top_k=10,
        )
    )

    call = client.query_points_calls[0]
    assert call["collection_name"] == "rag-test"
    assert len(call["prefetch"]) == 2
    assert call["query"].fusion == qdrant_models.Fusion.RRF
    assert [item.using for item in call["prefetch"]] == ["dense", "sparse"]
    sparse_query = call["prefetch"][1].query
    assert isinstance(sparse_query, qdrant_models.Document)
    assert sparse_query.model == "Qdrant/bm25"
    assert sparse_query.text == "AppBuilder API Key"
    assert chunks[0].chunk_id == "chunk-a"
    assert chunks[0].retrieval_channels == (
        RagRetrievalChannel.DENSE,
        RagRetrievalChannel.SPARSE,
    )


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
        self.query_response: Any = _QueryResponse([])

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
        return self.query_response


class _QueryResponse:
    def __init__(self, points: list[Any]) -> None:
        self.points = points


class _ScoredPoint:
    def __init__(self, *, score: float, payload: dict[str, Any]) -> None:
        self.score = score
        self.payload = payload


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
