"""模型生成派生产物使用的固定分类。"""

from enum import StrEnum


class GenerationArtifactKind(StrEnum):
    """当前允许持久化的两类生成派生结果。"""

    CONTEXTUAL_TEXT = "contextual_text"
    GRAPH_CANDIDATES = "graph_candidates"
