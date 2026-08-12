"""读取资源当前 applied revision 的 Mongo 辅助函数。"""

from rag.core.persistence.mongo.content_records import to_content_revision
from rag.domain.content_revision import ContentRevision
from rag.domain.entities import ContentRevisionEntity, ResourceIndexStateEntity


async def get_applied_revision(resource_id: str) -> ContentRevision | None:
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
    return to_content_revision(entity.model_dump())
