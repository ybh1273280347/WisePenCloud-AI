from __future__ import annotations

from typing import Any

from chat.application.rag.context_builder import RagDirectEvidence
from chat.application.rag.graph import RagGraphEvidence, RagOntologyHint
from chat.application.rag.knowledge_search import RagKnowledgeSearcher
from chat.application.rag.models import RagKnowledgeSearchRequest
from chat.application.rag.retrieval.models import (
    RagPermissionScope,
    RagRetrievalProfile,
)
from chat.application.tools.core import (
    ToolDefinition,
    ToolExecutionError,
    ToolLLMSpec,
    ToolParametersSchema,
    ToolPolicy,
    ToolRiskLevel,
)
from chat.application.tools.core.tool_return import ToolReturn
from chat.application.tools.tool_settings import tool_settings
from chat.core.config.app_settings import settings

MAX_RAG_STRING_ITEMS = 16

RAG_KNOWLEDGE_SEARCH_TOOL_DESCRIPTION = """\
Search the attached WisePen private knowledge base with ACL-safe RAG retrieval.

WHEN TO TRIGGER:
  - MUST trigger when the user asks a question that should be answered from an attached or selected WisePen knowledge resource.
  - SHOULD trigger before answering domain-specific questions when a resource_id is available in the current conversation context.
DO NOT TRIGGER when:
  - The user asks for open web or real-time information; use platform_search or web_fetch instead.
  - The user asks about previously parsed cnt_* content; use tool_content_rerank_read, tool_content_regex_read, or tool_content_sequential_read instead.
  - You do not know the target resource_id.

INPUT RULES:
  - query is the user's information need, not a rewritten hidden query plan.
  - resource_id identifies the target knowledge resource.
  - retrieval_profile is selected by you: balanced is default, semantic for fuzzy concepts, lexical for exact terms, error codes, function names, or quoted phrases.
  - keywords are optional exact content phrases for Elastic filtering; omit them unless the user supplied concrete terms.
  - Do not pass user_id, group roles, ACL data, Qdrant IDs, graph IDs, or internal storage IDs.

OUTPUT RULES:
  - The tool returns answerability status, citations, direct evidence summaries, graph evidence summaries, and optional cached RAG context.
  - If answerability.status is rejected, do not fabricate an answer; explain the reason or ask for clarification.
  - If warnings are present, answer conservatively using the evidence and mention limits when needed.
  - Treat citation_id plus page_label/section_path/anchor_labels as the model-facing direct evidence locator.
"""

# 只暴露模型能决定的语义字段；版本标识、权限范围和检索窗口都由系统边界注入。
PARAMETERS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "minLength": 1,
            "description": "Required. The user's knowledge-base question in the user's own language.",
        },
        "resource_id": {
            "type": "string",
            "minLength": 1,
            "description": "Required. The WisePen knowledge resource id to search.",
        },
        "retrieval_profile": {
            "type": "string",
            "enum": [profile.value for profile in RagRetrievalProfile],
            "default": RagRetrievalProfile.BALANCED.value,
            "description": "RAG retrieval intent selected by the model.",
        },
        "keywords": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "minItems": 1,
            "maxItems": MAX_RAG_STRING_ITEMS,
            "description": "Optional exact content phrases for Elastic keyword prefilter.",
        },
    },
    "required": ["query", "resource_id"],
    "additionalProperties": False,
}


class RagKnowledgeSearchTool:
    """WisePen 私有知识库 RAG 检索工具门面。"""

    __slots__ = ("_definition", "_searcher")

    def __init__(
            self,
            *,
            searcher: RagKnowledgeSearcher,
    ) -> None:
        self._searcher = searcher
        self._definition = ToolDefinition(
            llm_spec=ToolLLMSpec(
                name="rag_knowledge_search",
                description=RAG_KNOWLEDGE_SEARCH_TOOL_DESCRIPTION,
                parameters_schema=ToolParametersSchema(PARAMETERS_SCHEMA),
            ),
            policy=ToolPolicy(
                expose_by_default=True,
                persist_output=True,
                risk_level=ToolRiskLevel.LOW,
                required_context_keys=("user_id", "session_id"),
                timeout_seconds=tool_settings.RAG_KNOWLEDGE_SEARCH_TOOL_TIMEOUT_SECONDS,
                cache_chunked=True,
            ),
        )

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    async def execute(self, context: dict[str, Any], **kwargs: Any) -> ToolReturn:
        try:
            # top_k/candidate_limit/elastic_prefilter_limit 是调参项，固定从 app settings 读取。
            result = await self._searcher.search(
                RagKnowledgeSearchRequest(
                    query=kwargs["query"].strip(),
                    resource_id=kwargs["resource_id"].strip(),
                    retrieval_profile=RagRetrievalProfile(
                        kwargs.get("retrieval_profile") or RagRetrievalProfile.BALANCED.value
                    ),
                    keywords=tuple(
                        item.strip()
                        for item in kwargs.get("keywords", ())
                        if item.strip()
                    ),
                    permission_scope=RagPermissionScope(
                        user_id=str(context["user_id"]),
                        group_role_map={},
                    ),
                    session_id=str(context["session_id"]),
                    top_k=settings.RAG_KNOWLEDGE_SEARCH_TOP_K,
                    candidate_limit=settings.RAG_KNOWLEDGE_SEARCH_CANDIDATE_LIMIT,
                    elastic_prefilter_limit=(
                        settings.RAG_KNOWLEDGE_SEARCH_ELASTIC_PREFILTER_LIMIT
                    ),
                )
            )
        except ValueError as exc:
            raise ToolExecutionError(
                reason="rag_knowledge_search_invalid_request",
                detail_reason=str(exc),
                retryable=False,
            ) from exc

        return ToolReturn(
            tag="rag_knowledge_search_result",
            visible_result={
                "answerability": _answerability_payload(result),
                "direct_evidence": [
                    _direct_evidence_payload(evidence)
                    for evidence in result.direct_evidence
                ],
                "graph_evidence": [
                    _graph_evidence_payload(evidence)
                    for evidence in (
                        result.graph_enhancement.graph_evidence
                        if result.graph_enhancement is not None
                        else ()
                    )
                ],
                "ontology_hints": [
                    _ontology_hint_payload(hint)
                    for hint in (
                        result.graph_enhancement.ontology_hints
                        if result.graph_enhancement is not None
                        else ()
                    )
                ],
            },
            cacheable_texts=(
                (result.context.context_text,)
                if result.context is not None
                else ()
            ),
        )


def _answerability_payload(result: Any) -> dict[str, Any]:
    warning = result.answerability_warning
    payload = {
        "status": result.hard_gate.status.value,
        "reason": result.hard_gate.reason.value if result.hard_gate.reason is not None else None,
        "warnings": [reason.value for reason in warning.warnings] if warning is not None else [],
    }
    if warning is not None and warning.guidance.strip():
        payload["guidance"] = warning.guidance
    return payload


def _direct_evidence_payload(evidence: RagDirectEvidence) -> dict[str, Any]:
    return {
        "citation_id": evidence.citation_id,
        "document_version": evidence.document_version,
        "page_label": evidence.page_label,
        "section_path": list(evidence.section_path),
        "anchor_labels": list(evidence.anchor_labels),
        "excerpt": _excerpt(evidence.text),
    }


def _graph_evidence_payload(evidence: RagGraphEvidence) -> dict[str, Any]:
    return {
        "document_version": evidence.document_version,
        "page_label": evidence.page_label,
        "section_path": list(evidence.section_path),
        "anchor_labels": list(evidence.anchor_labels),
        "related_concepts": list(evidence.related_concepts),
        "excerpt": _excerpt(evidence.evidence_text),
    }


def _ontology_hint_payload(hint: RagOntologyHint) -> dict[str, Any]:
    return {
        "concept": hint.concept,
        "class_candidates": list(hint.class_candidates),
        "relation_type_candidates": list(hint.relation_type_candidates),
        "path_preview": list(hint.path_preview),
    }


def _excerpt(text: str, *, max_chars: int = 320) -> str:
    clean = " ".join(text.split())
    if len(clean) <= max_chars:
        return clean
    return f"{clean[:max_chars].rstrip()}..."
