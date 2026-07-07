from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum


class RagRetrievalChannel(StrEnum):
    DENSE = "dense"
    SPARSE = "sparse"


class RagRetrievalProfile(StrEnum):
    """主模型可选择的 RAG 检索意图。"""

    BALANCED = "balanced"  # 语义 + lexical 均衡
    SEMANTIC = "semantic"  # 偏重向量语义相似度
    LEXICAL = "lexical"  # 偏重关键词匹配
    ANCHORED_EXACT = "anchored_exact"  # 锚点或标题精确匹配，用于定位到具体段落


class RagGroupRole(StrEnum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    MEMBER = "MEMBER"


@dataclass(frozen=True, slots=True)
class RagPermissionScope:
    """当前请求的 RAG 检索权限范围。"""

    user_id: str
    group_role_map: dict[str, str]

    @property
    def managed_group_ids(self) -> tuple[str, ...]:
        return tuple(
            group_id
            for group_id, role in self.group_role_map.items()
            if role in {RagGroupRole.OWNER.value, RagGroupRole.ADMIN.value}
        )

    @property
    def joined_group_ids(self) -> tuple[str, ...]:
        return tuple(self.group_role_map)


@dataclass(frozen=True, slots=True)
class RagElasticKeywordFilterRequest:
    keywords: tuple[str, ...]
    resource_id: str
    permission_scope: RagPermissionScope | None = None
    limit: int = 1000


@dataclass(frozen=True, slots=True)
class RagQdrantRetrievalFilterRequest:
    resource_id: str
    candidate_chunk_ids: tuple[str, ...] = ()
    permission_scope: RagPermissionScope | None = None


@dataclass(frozen=True, slots=True)
class RagQdrantRetrievalRequest:
    resource_id: str
    query_text: str
    query_vector: Sequence[float]
    candidate_chunk_ids: tuple[str, ...] = ()
    permission_scope: RagPermissionScope | None = None
    top_k: int = 100


@dataclass(frozen=True, slots=True)
class ScoredChunk:
    """已经由上游检索层完成融合排序的 child chunk 候选。"""

    chunk_id: str  # child chunk id
    text: str  # 供 reranker 和多样性控制读取的证据文本
    retrieval_score: float | None = None  # 上游检索层返回的融合后分数；None 表示来源未提供分数
    retrieval_rank: int | None = None  # 上游检索层返回的原始排名，从 1 开始
    group_key: str | None = None  # 多样性控制分组键，例如同文档或同父 chunk
    resource_id: str = ""  # Qdrant payload 中的资源 ID，用于 direct evidence 归属
    document_version: str = ""  # 文档版本，用于回源和引用
    corpus_version: str = ""  # 检索语料版本
    parent_chunk_id: str = ""  # 父块 ID，用于上下文回填
    page_label: str | None = None  # 页码标签
    section_path: tuple[str, ...] = ()  # 章节路径
    anchor_labels: tuple[str, ...] = ()  # 表格、图片、公式等锚点标签
    retrieval_channels: tuple[RagRetrievalChannel, ...] = ()  # 命中的主召回通道
