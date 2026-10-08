"""Structural contexts used by RAG extraction.

Character-offset inline context is intentionally removed from the RAG Chunk
contract. The retrieval-context enhancement pipeline is a separate migration.
"""

from __future__ import annotations

from dataclasses import dataclass

from rag.application.document.models import DocChunk


class ContextMigrationRequired(RuntimeError):
    """请求了尚未迁移的 RAG 上下文能力，不能返回成功空结果。"""


@dataclass(frozen=True, slots=True)
class GraphExtractionContext:
    target_chunk_id: str
    section_path: tuple[str, ...]
    target_text: str


def build_graph_extraction_context(chunk: DocChunk) -> str:
    """Render target evidence separately from its section disambiguator."""

    context = GraphExtractionContext(
        chunk.chunk_id, tuple(chunk.section_path), chunk.raw_text
    )
    section_path = " > ".join(context.section_path) or "文档根"
    return (
        "<graph_extraction_context>\n"
        f"<section_path>\n{section_path}\n</section_path>\n\n"
        f'<target_chunk id="{context.target_chunk_id}">\n'
        f"{context.target_text}\n"
        "</target_chunk>\n"
        "</graph_extraction_context>"
    )
