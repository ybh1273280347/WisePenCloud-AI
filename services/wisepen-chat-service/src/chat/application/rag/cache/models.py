from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RagCacheLayer(StrEnum):
    """RAG 缓存层固定边界。"""

    INGESTION_DETERMINISTIC = "ingestion_deterministic"
    AUTHORIZED_EVIDENCE_MATERIALIZATION = "authorized_evidence_materialization"
    GRAPH_ENHANCEMENT = "graph_enhancement"
    RETRIEVAL_RUN_IDEMPOTENCY = "retrieval_run_idempotency"


@dataclass(frozen=True, slots=True)
class IngestionDeterministicCacheKey:
    """入库阶段确定性派生产物缓存 key。"""

    content_hash: str  # 文档内容 hash
    document_version: str  # 文档版本
    chunking_config_version: str  # 分块配置版本
    context_indexing_version: str  # Context Indexing prompt / model 版本
    embedding_model_version: str  # embedding 模型版本
    graph_extraction_version: str = ""  # 图抽取配置版本
    ontology_schema_version: str = ""  # 本体 schema 版本


@dataclass(frozen=True, slots=True)
class AuthorizedEvidenceMaterializationScope:
    """已授权 evidence 物化缓存作用域。"""

    user_id: str  # 当前用户
    session_id: str  # 当前会话
    kb_id: str  # 知识库边界
    acl_scope_hash: str  # ACL scope / projection epoch 摘要
    corpus_version: str  # corpus 版本


@dataclass(frozen=True, slots=True)
class AuthorizedEvidenceMaterializationCacheKey:
    """查询期已授权 evidence 物化缓存 key。"""

    scope: AuthorizedEvidenceMaterializationScope
    evidence_id: str  # direct evidence 或 graph evidence id
    document_version: str  # evidence 所属文档版本


@dataclass(frozen=True, slots=True)
class GraphEnhancementCacheKey:
    """Neo4j 图增强缓存 key。"""

    direct_evidence_signature: str  # direct evidence ids 的稳定签名
    answerability_warning_signature: str  # Soft Gate warning 的稳定签名
    graph_version: str  # 图数据版本
    ontology_schema_version: str  # 本体 schema 版本
    acl_scope_hash: str  # ACL scope / projection epoch 摘要
