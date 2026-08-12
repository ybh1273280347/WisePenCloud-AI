"""已发布文档结构读取 port 的 Beanie adapter。"""

from rag.core.persistence.mongo.mappers.deserializer import to_section
from rag.domain.entities import SectionEntity
from rag.domain.read_content import DocumentStructureResult
from rag.domain.repositories.applied_revision_reader import AppliedRevisionReader
from rag.domain.repositories.applied_structure_reader import AppliedStructureReader

from .applied_revision_reader import MongoAppliedRevisionReader


class MongoAppliedStructureReader(AppliedStructureReader):
    """只返回 applied revision 的结构事实，不读取正文。"""

    def __init__(self, revisions: AppliedRevisionReader | None = None) -> None:
        self._revisions = revisions or MongoAppliedRevisionReader()

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
            sections=[to_section(entity) for entity in entities],
        )
