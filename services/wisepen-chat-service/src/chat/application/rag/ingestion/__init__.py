"""RAG 入库阶段能力。

当前暴露父子分块与 Context Indexing，用于构建长期知识库索引输入。
"""

from .chunking import RagChunkingService
from .context_indexing import ContextIndexingError, ContextIndexingService
from .models import (
    ContextIndexingInput,
    ContextIndexingResult,
    RagChildChunk,
    RagChunkingResult,
    RagParentChunk,
)

# 包根只暴露入库阶段稳定 DTO 和 service，避免把 prompt 细节泄漏到外层。
__all__ = [
    "ContextIndexingError",
    "ContextIndexingInput",
    "ContextIndexingResult",
    "RagChildChunk",
    "RagChunkingResult",
    "RagChunkingService",
    "RagParentChunk",
    "ContextIndexingService",
]
