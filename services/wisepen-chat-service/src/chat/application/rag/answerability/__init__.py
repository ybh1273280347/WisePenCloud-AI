"""RAG 可回答性判断。

这里承接 retrieval 之后、context builder 之前的证据充分性判断。
"""

from .gate import AnswerabilityGate
from .models import (
    RagAnswerabilityDecision,
    RagAnswerabilityInput,
    RagAnswerabilityStatus,
    RagRefusalReason,
)

# 包根只暴露可回答性边界模型与门控入口。
__all__ = [
    "AnswerabilityGate",
    "RagAnswerabilityDecision",
    "RagAnswerabilityInput",
    "RagAnswerabilityStatus",
    "RagRefusalReason",
]
