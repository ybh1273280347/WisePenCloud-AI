"""模型生成结果缓存使用的固定分类。"""

from enum import StrEnum


class GenerationCacheKind(StrEnum):
    """当前允许持久化的两类生成派生结果。"""

    CONTEXTUAL_TEXT = "contextual_text"
    GRAPH_CANDIDATES = "graph_candidates"
