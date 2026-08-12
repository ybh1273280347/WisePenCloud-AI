"""领域检索事实到 Qdrant point 字段的序列化。"""

from typing import Any
from uuid import NAMESPACE_URL, uuid5

from rag.domain.acl import ResourceAcl
from rag.domain.retrieval import RetrievalChunk, SourceRef


def retrieval_point_id(content_revision: str, chunk_id: str) -> str:
    """为 revision 和 chunk 生成可重试复用的 Qdrant point ID。"""
    return str(
        uuid5(
            NAMESPACE_URL,
            f"wisepen-rag-v2-retrieval-chunk:{content_revision}:{chunk_id}",
        )
    )


def retrieval_point_payload(
    *,
    resource_id: str,
    content_revision: str,
    chunk: RetrievalChunk,
    source_ref: SourceRef,
    embedding_key: str,
    resource_acl: ResourceAcl,
    active: bool,
) -> dict[str, Any]:
    """序列化召回和最终回源需要的最小 payload。"""
    return {
        "resource_id": resource_id,
        "content_revision": content_revision,
        "active": active,
        "chunk_id": chunk.chunk_id,
        "reading_block_id": chunk.reading_block_id,
        "section_id": chunk.section_id,
        "raw_text": chunk.raw_text,
        "section_path": list(chunk.section_path),
        "anchor_labels": list(chunk.anchor_labels),
        "source_ref_id": source_ref.ref_id,
        "embedding_key": embedding_key,
        "acl_revision": resource_acl.acl_revision,
        "owner_id": resource_acl.owner_id,
        "readable_users": list(resource_acl.readable_users),
        "excluded_read_users": list(resource_acl.excluded_read_users),
        "group_acls": [
            {
                "group_id": group_acl.group_id,
                "is_readable": group_acl.default_readable,
                "readable_users": list(group_acl.readable_users),
                "excluded_read_users": list(group_acl.excluded_read_users),
            }
            for group_acl in resource_acl.group_acls
        ],
    }
