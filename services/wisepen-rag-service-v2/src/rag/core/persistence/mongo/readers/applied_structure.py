"""已发布文档结构读取 port 的 Beanie adapter。"""

from rag.domain.entities import SectionEntity
from rag.domain.models.structure import Section
from rag.domain.repositories.mongo.readers.applied_revision import AppliedRevisionReader
from rag.domain.repositories.mongo.readers.applied_structure import (
    AppliedStructureReader,
    AppliedStructureSnapshot,
)
from rag.utils.chunkers import SourceSpan


class MongoAppliedStructureReader(AppliedStructureReader):
    """只返回 applied revision 的结构事实，不读取正文。"""

    def __init__(self, *, revisions: AppliedRevisionReader) -> None:
        self._revisions = revisions

    async def get_applied_document_structure(
        self,
        resource_id: str,
    ) -> AppliedStructureSnapshot | None:
        revision = await self._revisions.get_applied_revision(resource_id)
        if revision is None:
            return None
        entities = (
            await SectionEntity.find(
                {
                    "resource_id": resource_id,
                    "content_revision": revision.content_revision,
                }
            )
            .sort("+own_start")
            .to_list()
        )
        sections = [_to_section(entity) for entity in entities]
        return AppliedStructureSnapshot(
            revision=revision,
            sections=sections,
            pages=list(revision.pages),
        )


def _to_section(record: SectionEntity) -> Section:
    return Section(
        section_id=record.section_id,
        title=record.title,
        level=record.level,
        parent_section_id=record.parent_section_id,
        ordinal=record.ordinal,
        section_path=list(record.section_path),
        own_span=SourceSpan(record.own_start, record.own_end),
        subtree_span=SourceSpan(record.own_start, record.subtree_end),
        content_spans=[
            SourceSpan(span.start_offset, span.end_offset)
            for span in record.content_spans
        ],
        preview=record.preview,
    )
