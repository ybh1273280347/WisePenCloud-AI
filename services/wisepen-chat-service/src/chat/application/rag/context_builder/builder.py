from __future__ import annotations

from chat.application.rag.graph import RagGraphEvidence, RagOntologyHint
from chat.application.utils.xml_markup import xml_attr, xml_cdata, xml_text

from .models import RagContextBuildRequest, RagContextPackage, RagDirectEvidence


class RagContextBuilder:
    """把 RAG direct evidence 渲染成主模型上下文。"""

    __slots__ = ()

    def build(self, request: RagContextBuildRequest) -> RagContextPackage:
        return RagContextPackage(
            query=request.query,
            direct_evidence=request.direct_evidence,
            context_text=_render_context_text(request),
            answerability_warning=request.answerability_warning,
            graph_evidence=request.graph_evidence,
            ontology_hints=request.ontology_hints,
        )


def _render_context_text(request: RagContextBuildRequest) -> str:
    evidence_blocks = [
        _render_evidence(evidence)
        for evidence in request.direct_evidence
    ]
    warning_block = _render_warning(request)
    graph_blocks = [
        _render_graph_evidence(evidence)
        for evidence in request.graph_evidence
    ]
    hint_blocks = [
        _render_ontology_hint(hint)
        for hint in request.ontology_hints
    ]
    return "\n".join(
        (
            "<rag_context>",
            f"  <user_query>{xml_cdata(request.query.strip())}</user_query>",
            "  <direct_evidence>",
            *evidence_blocks,
            "  </direct_evidence>",
            "  <graph_evidence>",
            *graph_blocks,
            "  </graph_evidence>",
            "  <ontology_hints>",
            *hint_blocks,
            "  </ontology_hints>",
            warning_block,
            "</rag_context>",
        )
    )


def _render_evidence(evidence: RagDirectEvidence) -> str:
    attrs = [
        f'citation_id="{xml_attr(evidence.citation_id)}"',
    ]
    if evidence.document_version:
        attrs.append(f'document_version="{xml_attr(evidence.document_version)}"')
    if evidence.page_label:
        attrs.append(f'page_label="{xml_attr(evidence.page_label)}"')

    locator_lines = []
    if evidence.section_path:
        locator_lines.append(
            f"      <section_path>{xml_text(' > '.join(evidence.section_path))}</section_path>"
        )
    if evidence.anchor_labels:
        locator_lines.append(
            f"      <anchor_labels>{xml_text(', '.join(evidence.anchor_labels))}</anchor_labels>"
        )

    return "\n".join(
        (
            f"    <evidence {' '.join(attrs)}>",
            *locator_lines,
            f"      <text>{xml_cdata(evidence.text.strip())}</text>",
            "    </evidence>",
        )
    )


def _render_warning(request: RagContextBuildRequest) -> str:
    warning = request.answerability_warning
    if warning is None or not warning.warnings:
        return "  <answerability_warning />"

    reasons = ", ".join(reason.value for reason in warning.warnings)
    return "\n".join(
        (
            "  <answerability_warning>",
            f"    <reasons>{xml_text(reasons)}</reasons>",
            f"    <guidance>{xml_cdata(warning.guidance)}</guidance>",
            "  </answerability_warning>",
        )
    )


def _render_graph_evidence(evidence: RagGraphEvidence) -> str:
    attrs = []
    if evidence.document_version:
        attrs.append(f'document_version="{xml_attr(evidence.document_version)}"')
    if evidence.page_label:
        attrs.append(f'page_label="{xml_attr(evidence.page_label)}"')

    locator_lines = []
    if evidence.section_path:
        locator_lines.append(
            f"      <section_path>{xml_text(' > '.join(evidence.section_path))}</section_path>"
        )
    if evidence.anchor_labels:
        locator_lines.append(
            f"      <anchor_labels>{xml_text(', '.join(evidence.anchor_labels))}</anchor_labels>"
        )

    return "\n".join(
        (
            f"    <evidence {' '.join(attrs)}>",
            *locator_lines,
            f"      <text>{xml_cdata(evidence.evidence_text.strip())}</text>",
            "    </evidence>",
        )
    )


def _render_ontology_hint(hint: RagOntologyHint) -> str:
    attrs = [f'concept="{xml_attr(hint.concept)}"']
    lines = [f"    <hint {' '.join(attrs)}>"]
    if hint.class_candidates:
        lines.append(
            f"      <class_candidates>{xml_text(', '.join(hint.class_candidates))}</class_candidates>"
        )
    if hint.relation_type_candidates:
        lines.append(
            "      <relation_type_candidates>"
            f"{xml_text(', '.join(hint.relation_type_candidates))}"
            "</relation_type_candidates>"
        )
    if hint.path_preview:
        lines.append(f"      <path_preview>{xml_text(' > '.join(hint.path_preview))}</path_preview>")
    lines.append("    </hint>")
    return "\n".join(lines)
