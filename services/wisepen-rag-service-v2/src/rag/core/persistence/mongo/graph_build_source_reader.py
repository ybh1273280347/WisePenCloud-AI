"""图构建输入读取 port 的 Beanie adapter。"""

from rag.core.persistence.mongo.mappers.deserializer import (
    to_reading_block,
    to_section,
    to_source_ref,
)
from rag.core.persistence.mongo.source_part_reader import MongoSourcePartReader
from rag.domain.entities import ReadingBlockEntity, SectionEntity, SourceRefEntity
from rag.domain.repositories.applied_revision_reader import AppliedRevisionReader
from rag.domain.repositories.graph_build_source_reader import (
    GraphBuildSource,
    GraphBuildSourceReader,
)
from rag.domain.services.text_assembler import assemble_source_text
from rag.utils.chunkers import SourceSpan

from .applied_revision_reader import MongoAppliedRevisionReader


class MongoGraphBuildSourceReader(GraphBuildSourceReader):
    """只为 index 图构建阶段读取指定 applied revision 的事实。"""

    def __init__(
        self,
        revisions: AppliedRevisionReader | None = None,
    ) -> None:
        self._revisions = revisions or MongoAppliedRevisionReader()
        self._source_parts = MongoSourcePartReader()

    async def get_graph_build_source(
        self,
        resource_id: str,
        content_revision: str,
    ) -> GraphBuildSource:
        revision = await self._revisions.get_applied_revision(resource_id)
        if revision is None or revision.content_revision != content_revision:
            raise RuntimeError(
                f"content revision {content_revision} is not applied for {resource_id}"
            )
        source_spans = [SourceSpan(0, revision.total_length)]
        parts = await self._source_parts.get_parts(
            content_revision,
            source_spans,
        )
        markdown = assemble_source_text(parts, source_spans)
        sections = await SectionEntity.find(
            {"resource_id": resource_id, "content_revision": content_revision}
        ).to_list()
        blocks = await ReadingBlockEntity.find(
            {"resource_id": resource_id, "content_revision": content_revision}
        ).sort([("section_id", 1), ("ordinal", 1)]).to_list()
        refs = await SourceRefEntity.find(
            {"resource_id": resource_id, "content_revision": content_revision}
        ).to_list()
        return GraphBuildSource(
            resource_id=resource_id,
            content_revision=content_revision,
            markdown=markdown,
            sections=[to_section(entity) for entity in sections],
            reading_blocks=[to_reading_block(entity) for entity in blocks],
            source_refs=[to_source_ref(entity) for entity in refs],
        )
