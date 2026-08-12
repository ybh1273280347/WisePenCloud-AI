"""模型生成缓存的 Beanie Mongo 实体。"""

from typing import ClassVar

from beanie import Document
from pymongo import ASCENDING, IndexModel

from rag.domain.models.generation import GenerationCacheKind


class GenerationArtifactEntity(Document):
    """按资源和生成类别保存可复用的模型输出。"""

    resource_id: str
    cache_kind: GenerationCacheKind
    cache_key: str
    payload: str

    class Settings:
        name = "wisepen_rag_v2_generation_artifact_store"
        indexes: ClassVar[list[IndexModel]] = [
            IndexModel(
                [
                    ("resource_id", ASCENDING),
                    ("cache_kind", ASCENDING),
                    ("cache_key", ASCENDING),
                ],
                name="idx_rag_v2_generation_cache_resource_kind_key",
                unique=True,
            ),
        ]
