"""图构建读取所需的已发布内容事实契约。"""

from dataclasses import dataclass, field
from typing import Protocol

from rag.domain.models.content import ReadingBlock
from rag.domain.models.retrieval import SourceRef
from rag.domain.models.structure import Section, StructureMode


@dataclass(slots=True)
class GraphBuildSource:
    """同一 applied revision 的图构建输入，不是通用内容读取结果。"""

    resource_id: str
    content_revision: str
    structure_mode: StructureMode
    markdown: str
    sections: list[Section] = field(default_factory=list)
    reading_blocks: list[ReadingBlock] = field(default_factory=list)
    source_refs: list[SourceRef] = field(default_factory=list)


class GraphBuildSourceReader(Protocol):
    """为 index 内图构建阶段读取已发布内容事实。"""

    async def get_graph_build_source(
        self,
        resource_id: str,
        content_revision: str,
    ) -> GraphBuildSource: ...
