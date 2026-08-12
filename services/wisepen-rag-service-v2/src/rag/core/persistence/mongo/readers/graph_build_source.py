"""图构建输入读取 port 的 Beanie adapter。"""

from rag.domain.document_structure import Section
from rag.domain.entities import ReadingBlockEntity, SectionEntity, SourceRefEntity
from rag.domain.reading import ReadingBlock
from rag.domain.repositories.applied_revision_reader import AppliedRevisionReader
from rag.domain.repositories.graph_build_source_reader import (
    GraphBuildSource,
    GraphBuildSourceReader,
)
from rag.domain.repositories.source_part_reader import SourcePartReader
from rag.domain.retrieval import SourceRef
from rag.domain.services.text_assembler import assemble_source_text
from rag.utils.chunkers import SourceSpan


class MongoGraphBuildSourceReader(GraphBuildSourceReader):
    """只为图构建阶段读取指定 applied revision 的完整输入。"""

    def __init__(
        self,
        *,
        revisions: AppliedRevisionReader,
        source_parts: SourcePartReader,
    ) -> None:
        self._revisions = revisions
        self._source_parts = source_parts

    async def get_graph_build_source(
        self,
        resource_id: str,
        content_revision: str,
    ) -> GraphBuildSource:
        revision = await self._revisions.get_applied_revision(resource_id)
        if revision is None or revision.content_revision != content_revision:
            raise RuntimeError(
                f"content revision {content_revision} is not applied for {resource_id}"
            )

        source_spans = [SourceSpan(0, revision.total_length)]
        parts = await self._source_parts.get_parts(content_revision, source_spans)
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
            markdown=assemble_source_text(parts, source_spans),
            sections=[_to_section(entity) for entity in sections],
            reading_blocks=[_to_reading_block(entity) for entity in blocks],
            source_refs=[_to_source_ref(entity) for entity in refs],
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
        preview=record.preview,
    )


def _to_reading_block(record: ReadingBlockEntity) -> ReadingBlock:
    return ReadingBlock(
        block_id=record.block_id,
        section_id=record.section_id,
        ordinal=record.ordinal,
        raw_text=record.raw_text,
        source_spans=[
            SourceSpan(span.start_offset, span.end_offset)
            for span in record.source_spans
        ],
        page_labels=list(record.page_labels),
        anchor_labels=list(record.anchor_labels),
    )


def _to_source_ref(record: SourceRefEntity) -> SourceRef:
    return SourceRef(
        ref_id=record.ref_id,
        resource_id=record.resource_id,
        content_revision=record.content_revision,
        chunk_id=record.chunk_id,
        reading_block_id=record.reading_block_id,
        section_id=record.section_id,
        section_path=list(record.section_path),
        source_spans=[
            SourceSpan(span.start_offset, span.end_offset)
            for span in record.source_spans
        ],
        page_labels=list(record.page_labels),
        anchor_labels=list(record.anchor_labels),
    )
