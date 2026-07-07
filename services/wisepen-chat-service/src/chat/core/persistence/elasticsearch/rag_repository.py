from __future__ import annotations

from typing import Any

from elasticsearch import AsyncElasticsearch
from elasticsearch.helpers import async_bulk

from chat.application.rag.acl import RagResourceAclProjection


class RagElasticRepository:
    """RAG child chunk 的 Elasticsearch strict prefilter 边界。"""

    __slots__ = ("_client", "_index_name")

    def __init__(
            self,
            *,
            client: AsyncElasticsearch | None,
            index_name: str,
    ) -> None:
        self._client = client
        self._index_name = index_name

    async def upsert_child_chunks(
            self,
            *,
            child_chunks: tuple[Any, ...],
            resource_id: str,
            document_version: str,
            corpus_version: str,
            acl_projection: RagResourceAclProjection | None = None,
    ) -> None:
        if self._client is None:
            return

        await self._delete_document_chunks(
            resource_id=resource_id,
            document_version=document_version,
        )
        if not child_chunks:
            return

        actions = (
            {
                "_op_type": "index",
                "_index": self._index_name,
                "_id": child.chunk_id,
                **self._build_child_document(
                    child,
                    resource_id=resource_id,
                    document_version=document_version,
                    corpus_version=corpus_version,
                    acl_projection=acl_projection,
                ),
            }
            for child in child_chunks
        )
        await async_bulk(self._client, actions)

    async def update_acl_projection(self, projection: RagResourceAclProjection) -> None:
        if self._client is None:
            return

        await self._client.update_by_query(
            index=self._index_name,
            query={
                "bool": {
                    "filter": [
                        {"term": {"resource_id": projection.resource_id}},
                    ]
                }
            },
            script={
                "source": (
                    "ctx._source.owner_id = params.owner_id; "
                    "ctx._source.readable_users = params.readable_users; "
                    "ctx._source.computed_group_acls = params.computed_group_acls;"
                ),
                "params": _build_acl_document(projection),
            },
            refresh=False,
        )

    async def _delete_document_chunks(
            self,
            *,
            resource_id: str,
            document_version: str,
    ) -> None:
        await self._client.delete_by_query(
            index=self._index_name,
            query={
                "bool": {
                    "filter": [
                        {"term": {"resource_id": resource_id}},
                        {"term": {"document_version": document_version}},
                    ]
                }
            },
            conflicts="proceed",
            ignore_unavailable=True,
            refresh=False,
        )

    def _build_child_document(
            self,
            child: Any,
            *,
            resource_id: str,
            document_version: str,
            corpus_version: str,
            acl_projection: RagResourceAclProjection | None,
    ) -> dict[str, Any]:
        document = {
            "chunk_id": child.chunk_id,
            "parent_chunk_id": child.parent_chunk_id,
            "resource_id": resource_id,
            "document_version": document_version,
            "corpus_version": corpus_version,
            "content_hash": child.content_hash,
            "indexing_text": child.indexing_text or child.text,
            "evidence_text": child.text,
            "page_label": child.page_label,
            "section_path": list(child.section_path),
            "section_path_text": " > ".join(child.section_path),
            "anchor_labels": list(child.anchor_labels),
            "start_offset": child.start_offset,
            "end_offset": child.end_offset,
        }
        # indexing_text 仅服务关键词 prefilter；version 字段只用于投影替换和引用标识。
        if acl_projection is None:
            return document

        document.update(_build_acl_document(acl_projection))
        return document


def _build_acl_document(projection: RagResourceAclProjection) -> dict[str, Any]:
    return {
        "owner_id": projection.owner_id,
        "readable_users": list(projection.readable_users),
        "computed_group_acls": [
            {
                "group_id": item.group_id,
                "is_readable": item.is_readable,
                "readable_users": list(item.readable_users),
                "excluded_read_users": list(item.excluded_read_users),
            }
            for item in projection.computed_group_acls
        ],
    }
