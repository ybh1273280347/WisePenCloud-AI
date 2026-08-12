"""当前 applied revision 查询的 Beanie adapter。"""

from rag.domain.content_revision import ContentRevision
from rag.domain.document_structure import PageRange, StructureMode
from rag.domain.entities import ContentRevisionEntity, ResourceIndexStateEntity
from rag.domain.repositories.applied_revision_reader import AppliedRevisionReader
from rag.utils.chunkers import SourceSpan


class MongoAppliedRevisionReader(AppliedRevisionReader):
    """只查询资源当前 applied revision，不负责正文或结构读取。"""

    async def get_applied_revision(self, resource_id: str):
        state = await ResourceIndexStateEntity.find_one({"resource_id": resource_id})
        if state is None or state.applied_content_revision is None:
            return None
        entity = await ContentRevisionEntity.find_one(
            {
                "resource_id": resource_id,
                "content_revision": state.applied_content_revision,
            }
        )
        if entity is None:
            raise RuntimeError(f"resource {resource_id} applied revision is missing")
        return _to_domain(entity)


def _to_domain(record: ContentRevisionEntity) -> ContentRevision:
    return ContentRevision(
        resource_id=record.resource_id,
        content_revision=record.content_revision,
        document_version=record.document_version,
        content_hash=record.content_hash,
        index_schema_version=record.index_schema_version,
        structure_mode=StructureMode(record.structure_mode),
        total_length=record.total_length,
        pages=[
            PageRange(
                page_index=page.page_index,
                page_label=page.page_label,
                source_span=SourceSpan(page.start_offset, page.end_offset),
            )
            for page in record.pages
        ],
    )
