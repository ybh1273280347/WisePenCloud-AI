"""图构建输入读取 port 的 Beanie adapter。"""

from rag.core.persistence.mongo.applied_revision import get_applied_revision
from rag.core.persistence.mongo.content_records import (
    to_reading_block,
    to_section,
    to_source_ref,
)
from rag.core.persistence.mongo.source_text import get_source_text
from rag.domain.entities import ReadingBlockEntity, SectionEntity, SourceRefEntity
from rag.domain.repositories.graph_build_source_reader import (
    GraphBuildSource,
    GraphBuildSourceReader,
)
from rag.utils.chunkers import SourceSpan


class MongoGraphBuildSourceReader(GraphBuildSourceReader):
    """只为 index 图构建阶段读取指定 applied revision 的事实。"""

    async def get_graph_build_source(
        self,
        resource_id: str,
        content_revision: str,
    ) -> GraphBuildSource:
        revision = await get_applied_revision(resource_id)
        if revision is None or revision.content_revision != content_revision:
            raise RuntimeError(
                f"content revision {content_revision} is not applied for {resource_id}"
            )
        markdown = await get_source_text(
            content_revision,
            [SourceSpan(0, revision.total_length)],
        )
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
            sections=[to_section(entity.model_dump()) for entity in sections],
            reading_blocks=[to_reading_block(entity.model_dump()) for entity in blocks],
            source_refs=[to_source_ref(entity.model_dump()) for entity in refs],
        )
