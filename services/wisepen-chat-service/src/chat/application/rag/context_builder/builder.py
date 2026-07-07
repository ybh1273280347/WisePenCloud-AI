from __future__ import annotations

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
        )


def _render_context_text(request: RagContextBuildRequest) -> str:
    evidence_blocks = [
        _render_evidence(evidence)
        for evidence in request.direct_evidence
    ]
    warning_block = _render_warning(request)
    return "\n".join(
        (
            "<rag_context>",
            f"  <user_query>{xml_cdata(request.query.strip())}</user_query>",
            "  <direct_evidence>",
            *evidence_blocks,
            "  </direct_evidence>",
            warning_block,
            "</rag_context>",
        )
    )


def _render_evidence(evidence: RagDirectEvidence) -> str:
    attrs = [
        f'citation_id="{xml_attr(evidence.citation_id)}"',
        f'parent_chunk_id="{xml_attr(evidence.parent_chunk_id)}"',
        f'citation_anchor="{xml_attr(evidence.citation_anchor)}"',
        f'rank="{evidence.rank}"',
        f'score="{evidence.score:.6f}"',
    ]
    if evidence.resource_id:
        attrs.append(f'resource_id="{xml_attr(evidence.resource_id)}"')
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
    if evidence.matched_child_chunks:
        locator_lines.append(_render_matched_child_chunks(evidence))

    return "\n".join(
        (
            f"    <evidence {' '.join(attrs)}>",
            *locator_lines,
            f"      <text>{xml_cdata(evidence.text.strip())}</text>",
            "    </evidence>",
        )
    )


def _render_matched_child_chunks(evidence: RagDirectEvidence) -> str:
    lines = ["      <matched_child_chunks>"]
    for child in evidence.matched_child_chunks:
        attrs = [f'chunk_id="{xml_attr(child.chunk_id)}"']
        if child.page_label:
            attrs.append(f'page_label="{xml_attr(child.page_label)}"')
        lines.append(f"        <child {' '.join(attrs)}>")
        if child.section_path:
            lines.append(
                f"          <section_path>{xml_text(' > '.join(child.section_path))}</section_path>"
            )
        if child.anchor_labels:
            lines.append(
                f"          <anchor_labels>{xml_text(', '.join(child.anchor_labels))}</anchor_labels>"
            )
        if child.retrieval_channels:
            lines.append(
                "          <retrieval_channels>"
                f"{xml_text(', '.join(channel.value for channel in child.retrieval_channels))}"
                "</retrieval_channels>"
            )
        lines.append("        </child>")
    lines.append("      </matched_child_chunks>")
    return "\n".join(lines)


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
