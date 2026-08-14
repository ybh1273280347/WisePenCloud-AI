"""INDEX 内部的内容、检索和图谱构建函数。"""

from .graph_merge import merge_candidate_graph
from .reading_blocks import build_flat_text_sections, build_reading_blocks
from .retrieval_chunks import build_retrieval_chunks
from .revisions import build_content_revision_id, create_content_revision
from .source_refs import build_source_refs
from .structure import parse_document_structure

__all__ = [
    "build_content_revision_id",
    "build_flat_text_sections",
    "build_reading_blocks",
    "build_retrieval_chunks",
    "build_source_refs",
    "create_content_revision",
    "merge_candidate_graph",
    "parse_document_structure",
]
