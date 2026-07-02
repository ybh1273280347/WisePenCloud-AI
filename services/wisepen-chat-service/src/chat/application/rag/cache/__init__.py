"""RAG 缓存边界占位。

缓存只优化入库派生产物、已授权 evidence 物化和图增强中间结果，
不缓存 query 结果或 final answer。
"""

from .evidence_materialization import AuthorizedEvidenceMaterializationCache
from .graph_enhancement import GraphEnhancementCache
from .ingestion_deterministic import IngestionDeterministicCache
from .models import (
    AuthorizedEvidenceMaterializationCacheKey,
    AuthorizedEvidenceMaterializationScope,
    GraphEnhancementCacheKey,
    IngestionDeterministicCacheKey,
    RagCacheLayer,
)

__all__ = [
    "AuthorizedEvidenceMaterializationCache",
    "AuthorizedEvidenceMaterializationCacheKey",
    "AuthorizedEvidenceMaterializationScope",
    "GraphEnhancementCache",
    "GraphEnhancementCacheKey",
    "IngestionDeterministicCache",
    "IngestionDeterministicCacheKey",
    "RagCacheLayer",
]
