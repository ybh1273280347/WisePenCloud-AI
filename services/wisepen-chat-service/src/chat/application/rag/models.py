from __future__ import annotations

from dataclasses import dataclass

from chat.application.rag.answerability import RagAnswerabilityWarning, RagHardGateDecision
from chat.application.rag.context_builder import RagContextPackage, RagDirectEvidence
from chat.application.rag.graph import RagGraphEnhancementResult
from chat.application.rag.retrieval import (
    RagPermissionScope,
    RagRetrievalProfile,
)


@dataclass(frozen=True, slots=True)
class RagKnowledgeSearchRequest:
    query: str  # 模型可传入的用户问题，不承载隐藏检索计划。
    resource_id: str  # 模型可传入的知识库资源定位。
    retrieval_profile: RagRetrievalProfile = RagRetrievalProfile.BALANCED  # 模型只选择检索意图。
    keywords: tuple[str, ...] = ()  # 模型只在用户给出明确词面时传入，供 Elastic 内容 prefilter 使用。
    permission_scope: RagPermissionScope | None = None
    session_id: str = ""
    top_k: int = 8  # tool settings 注入的调参项，不能从模型 schema 暴露。
    candidate_limit: int = 80  # tool settings 注入的调参项，不能从模型 schema 暴露。
    elastic_prefilter_limit: int = 1000  # tool settings 注入的调参项，不能从模型 schema 暴露。


@dataclass(frozen=True, slots=True)
class RagKnowledgeSearchResult:
    hard_gate: RagHardGateDecision
    direct_evidence: tuple[RagDirectEvidence, ...] = ()
    answerability_warning: RagAnswerabilityWarning | None = None
    graph_enhancement: RagGraphEnhancementResult | None = None
    context: RagContextPackage | None = None

    @property
    def should_continue(self) -> bool:
        return self.hard_gate.should_continue
