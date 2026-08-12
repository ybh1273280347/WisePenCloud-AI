"""权威原文分片读取 port 的 Beanie adapter。"""

from collections.abc import Sequence

from rag.domain.content_revision import SourcePart
from rag.domain.entities import SourcePartEntity
from rag.domain.mappers import to_source_part
from rag.domain.repositories.source_part_reader import SourcePartReader
from rag.utils.chunkers import SourceSpan


class MongoSourcePartReader(SourcePartReader):
    """只负责按 revision 和范围查询 SourcePart，不组装文本。"""

    async def get_parts(
        self,
        content_revision: str,
        source_spans: Sequence[SourceSpan] | None = None,
    ) -> list[SourcePart]:
        query: dict[str, object] = {"content_revision": content_revision}
        if source_spans:
            query.update(
                {
                    "start_offset": {
                        "$lt": max(span.end_offset for span in source_spans)
                    },
                    "end_offset": {
                        "$gt": min(span.start_offset for span in source_spans)
                    },
                }
            )
        entities = await SourcePartEntity.find(query).sort("+part_index").to_list()
        return [to_source_part(entity) for entity in entities]
