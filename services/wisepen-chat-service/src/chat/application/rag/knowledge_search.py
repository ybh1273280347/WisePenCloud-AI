from __future__ import annotations

from chat.application.rag.context_builder import (
    RagContextBuildRequest,
    RagContextBuilder,
)
from chat.application.rag.models import (
    RagKnowledgeSearchRequest,
    RagKnowledgeSearchResult,
)
from chat.application.rag.retrieval.retrieval_pipeline import (
    RagRetrievalPipeline,
    RagRetrievalPipelineRequest,
)


class RagKnowledgeSearcher:
    """执行定稿中的 RAG 主检索链路。"""

    __slots__ = (
        "_context_builder",
        "_retrieval_pipeline",
    )

    def __init__(
            self,
            *,
            retrieval_pipeline: RagRetrievalPipeline,
            context_builder: RagContextBuilder,
    ) -> None:
        self._retrieval_pipeline = retrieval_pipeline
        self._context_builder = context_builder

    async def search(self, request: RagKnowledgeSearchRequest) -> RagKnowledgeSearchResult:
        retrieval = await self._retrieval_pipeline.retrieve(
            RagRetrievalPipelineRequest(
                query=request.query,
                resource_id=request.resource_id,
                session_id=request.session_id,
                retrieval_profile=request.retrieval_profile,
                keywords=request.keywords,
                permission_scope=request.permission_scope,
                top_k=request.top_k,
                candidate_limit=request.candidate_limit,
                elastic_prefilter_limit=request.elastic_prefilter_limit,
            )
        )

        hard_gate = retrieval.hard_gate
        if hard_gate is None:
            raise RuntimeError("RagRetrievalPipeline must be configured with answerability gates.")
        if not hard_gate.should_continue:
            return RagKnowledgeSearchResult(
                hard_gate=hard_gate,
            )

        direct_evidence = retrieval.direct_evidence
        warning = retrieval.answerability_warning
        graph_enhancement = retrieval.graph_enhancement
        context = self._context_builder.build(
            RagContextBuildRequest(
                query=request.query,
                direct_evidence=direct_evidence,
                answerability_warning=warning,
                graph_evidence=graph_enhancement.graph_evidence,
                ontology_hints=graph_enhancement.ontology_hints,
            )
        )
        return RagKnowledgeSearchResult(
            hard_gate=hard_gate,
            direct_evidence=direct_evidence,
            answerability_warning=warning,
            graph_enhancement=graph_enhancement,
            context=context,
        )
