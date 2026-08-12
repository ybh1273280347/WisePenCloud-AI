"""已发布文档结构读取 port 的 Beanie adapter。"""

from rag.domain.document_structure import Section
from rag.domain.entities import SectionEntity
from rag.domain.read_content import DocumentStructureResult
from rag.domain.repositories.mongo.readers.applied_revision import AppliedRevisionReader
from rag.domain.repositories.mongo.readers.applied_structure import AppliedStructureReader
from rag.utils.chunkers import SourceSpan


class MongoAppliedStructureReader(AppliedStructureReader):
    """只返回 applied revision 的结构事实，不读取正文。"""

    def __init__(self, *, revisions: AppliedRevisionReader) -> None:
        self._revisions = revisions

    async def get_applied_document_structure(
        self,
        resource_id: str,
    ) -> DocumentStructureResult | None:
        revision = await self._revisions.get_applied_revision(resource_id)
        if revision is None:
            return None
        entities = await SectionEntity.find(
            {
                "resource_id": resource_id,
                "content_revision": revision.content_revision,
            }
        ).sort("+own_start").to_list()
        return DocumentStructureResult(
            revision=revision,
            sections=[_to_domain(entity) for entity in entities],
        )


def _to_domain(record: SectionEntity) -> Section:
    return Section(
        section_id=record.section_id,
        title=record.title,
        level=record.level,
        parent_section_id=record.parent_section_id,
        ordinal=record.ordinal,
        section_path=list(record.section_path),
        own_span=SourceSpan(record.own_start, record.own_end),
        subtree_span=SourceSpan(record.own_start, record.subtree_end),
        preview=record.preview,
    )
