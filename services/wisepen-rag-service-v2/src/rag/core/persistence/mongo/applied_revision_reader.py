"""当前 applied revision 查询的 Beanie adapter。"""

from rag.core.persistence.mongo.mappers.deserializer import to_content_revision
from rag.domain.entities import ContentRevisionEntity, ResourceIndexStateEntity
from rag.domain.repositories.applied_revision_reader import AppliedRevisionReader


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
        return to_content_revision(entity)
