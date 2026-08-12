"""从已存储 source parts 还原权威 Markdown 片段。"""

from collections.abc import Sequence

from rag.core.persistence.mongo.content_records import read_source_spans
from rag.domain.entities import SourcePartEntity
from rag.utils.chunkers import SourceSpan


async def get_source_text(
    content_revision: str,
    source_spans: Sequence[SourceSpan],
) -> str:
    if not source_spans:
        return ""
    entities = await SourcePartEntity.find(
        {
            "content_revision": content_revision,
            "start_offset": {"$lt": max(span.end_offset for span in source_spans)},
            "end_offset": {"$gt": min(span.start_offset for span in source_spans)},
        }
    ).sort("+part_index").to_list()
    return read_source_spans(
        content_revision=content_revision,
        documents=[entity.model_dump() for entity in entities],
        source_spans=source_spans,
    )
