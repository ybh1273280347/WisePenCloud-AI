"""从 Mongo 读取当前已发布资源的统一 adapter。"""

from collections.abc import Sequence
from hashlib import sha256

from rag.domain.entities import (
    ContentRevisionEntity,
    ReadingBlockEntity,
    ResourceIndexStateEntity,
    SectionEntity,
    SourcePartEntity,
    SourceRefEntity,
)
from rag.domain.models.content import (
    ContentRevision,
    ContentWindow,
    PublishedDocumentStructure,
    ReadingBlock,
    SectionContent,
    SectionFrontier,
    SourcePart,
)
from rag.domain.models.graph import GraphBuildSource
from rag.domain.models.provenance import SourceEvidence, SourceRef
from rag.domain.models.structure import (
    DocumentAnchor,
    PageRange,
    Section,
    StructureMode,
)
from rag.domain.repositories.mongo.published_resource_reader import (
    PublishedResourceCorruptError,
    PublishedResourceReader,
    PublishedResourceRevisionError,
)
from rag.utils.chunkers import SourceSpan


class MongoPublishedResourceReader(PublishedResourceReader):
    """统一读取一个资源当前发布 revision 的结构、正文和来源证据。"""

    async def get_revision(self, resource_id: str) -> ContentRevision | None:
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
            raise PublishedResourceCorruptError(
                f"resource {resource_id} published revision is missing"
            )
        return _to_content_revision(entity)

    async def get_document_structure(
        self,
        resource_id: str,
    ) -> PublishedDocumentStructure | None:
        revision = await self.get_revision(resource_id)
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
        return PublishedDocumentStructure(
            revision=revision,
            sections=[_to_section(entity) for entity in entities],
        )

    async def get_pages(
        self,
        resource_id: str,
        page_labels: Sequence[str],
    ) -> dict[str, ContentWindow] | None:
        revision = await self.get_revision(resource_id)
        if revision is None:
            return None

        pages_by_label = {page.page_label: page for page in revision.pages}
        selected_pages = [
            pages_by_label[label]
            for label in dict.fromkeys(page_labels)
            if label in pages_by_label
        ]
        all_sections = await self._get_sections_for_revision(
            resource_id,
            revision.content_revision,
        )

        windows: dict[str, ContentWindow] = {}
        for page in selected_pages:
            parts = await self._get_parts(
                revision.content_revision,
                [page.source_span],
            )
            # Page 入口来自标题或权威直属正文的交集，不借用检索分块推断结构。
            sections = [
                section
                for section in all_sections
                if page.source_span.start_offset
                <= section.own_span.start_offset
                < page.source_span.end_offset
                or any(
                    _overlaps(span, page.source_span) for span in section.content_spans
                )
            ]
            windows[page.page_label] = ContentWindow(
                text=_assemble_source_text(parts, [page.source_span]),
                source_span=page.source_span,
                page_labels=[page.page_label],
                sections=sections,
                anchor_labels=list(
                    dict.fromkeys(
                        anchor.label
                        for anchor in revision.anchors
                        if _overlaps(anchor.source_span, page.source_span)
                    )
                ),
            )
        return windows

    async def get_sections(
        self,
        resource_id: str,
        section_ids: Sequence[str],
    ) -> dict[str, SectionContent] | None:
        revision = await self.get_revision(resource_id)
        if revision is None:
            return None

        requested_ids = list(dict.fromkeys(section_ids))
        if not requested_ids:
            return {}

        all_sections = await self._get_sections_for_revision(
            resource_id,
            revision.content_revision,
        )
        sections_by_id = {section.section_id: section for section in all_sections}
        selected = [
            sections_by_id[section_id]
            for section_id in requested_ids
            if section_id in sections_by_id
        ]
        if not selected:
            return {}

        requested_spans = [
            span for section in selected for span in section.content_spans
        ]
        parts = (
            await self._get_parts(revision.content_revision, requested_spans)
            if requested_spans
            else []
        )
        siblings_by_parent: dict[str | None, list[Section]] = {}
        for section in all_sections:
            siblings_by_parent.setdefault(section.parent_section_id, []).append(section)
        for siblings in siblings_by_parent.values():
            siblings.sort(key=lambda section: section.ordinal)

        result: dict[str, SectionContent] = {}
        for section in selected:
            siblings = siblings_by_parent[section.parent_section_id]
            index = next(
                index
                for index, sibling in enumerate(siblings)
                if sibling.section_id == section.section_id
            )
            result[section.section_id] = SectionContent(
                section=section,
                text=_assemble_source_text(parts, section.content_spans),
                page_labels=_overlapping_labels(
                    section.content_spans,
                    revision.pages,
                ),
                anchor_labels=_overlapping_labels(
                    section.content_spans,
                    revision.anchors,
                ),
                frontier=SectionFrontier(
                    parent=sections_by_id.get(section.parent_section_id),
                    previous=siblings[index - 1] if index else None,
                    next=siblings[index + 1] if index + 1 < len(siblings) else None,
                    children=siblings_by_parent.get(section.section_id, []),
                ),
            )
        return result

    async def get_source_evidence(
        self,
        resource_id: str,
        content_revision: str,
        source_ref_ids: Sequence[str],
    ) -> dict[str, SourceEvidence] | None:
        revision = await self.get_revision(resource_id)
        if revision is None:
            return None
        self._require_revision(revision, content_revision)

        full_span = SourceSpan(0, revision.total_length)
        parts = await self._get_parts(content_revision, [full_span])
        full_text = _assemble_source_text(parts, [full_span])
        if sha256(full_text.encode("utf-8")).hexdigest() != revision.content_hash:
            raise PublishedResourceCorruptError(
                f"content revision {content_revision} hash does not match source parts"
            )

        requested_ids = list(dict.fromkeys(source_ref_ids))
        if not requested_ids:
            return {}
        ref_entities = await SourceRefEntity.find(
            {
                "resource_id": resource_id,
                "content_revision": content_revision,
                "ref_id": {"$in": requested_ids},
            }
        ).to_list()
        refs = [_to_source_ref(entity) for entity in ref_entities]

        blocks = await ReadingBlockEntity.find(
            {
                "resource_id": resource_id,
                "content_revision": content_revision,
                "block_id": {"$in": list({ref.reading_block_id for ref in refs})},
            }
        ).to_list()
        sections = await SectionEntity.find(
            {
                "resource_id": resource_id,
                "content_revision": content_revision,
                "section_id": {"$in": list({ref.section_id for ref in refs})},
            }
        ).to_list()
        blocks_by_id = {entity.block_id: _to_reading_block(entity) for entity in blocks}
        sections_by_id = {entity.section_id: _to_section(entity) for entity in sections}

        evidence: dict[str, SourceEvidence] = {}
        for source_ref in refs:
            block = blocks_by_id.get(source_ref.reading_block_id)
            section = sections_by_id.get(source_ref.section_id)
            if block is None or section is None:
                raise PublishedResourceCorruptError(
                    f"source ref {source_ref.ref_id} has missing ownership records"
                )
            evidence[source_ref.ref_id] = SourceEvidence(
                revision=revision,
                source_ref=source_ref,
                reading_block=block,
                section=section,
                source_text=_assemble_source_text(parts, source_ref.source_spans),
            )
        return evidence

    async def get_graph_build_source(
        self,
        resource_id: str,
        content_revision: str,
    ) -> GraphBuildSource:
        revision = await self.get_revision(resource_id)
        if revision is None:
            raise PublishedResourceRevisionError(
                f"resource {resource_id} has no published revision"
            )
        self._require_revision(revision, content_revision)

        full_span = SourceSpan(0, revision.total_length)
        parts = await self._get_parts(content_revision, [full_span])
        sections = await SectionEntity.find(
            {"resource_id": resource_id, "content_revision": content_revision}
        ).to_list()
        blocks = (
            await ReadingBlockEntity.find(
                {"resource_id": resource_id, "content_revision": content_revision}
            )
            .sort([("start_offset", 1), ("ordinal", 1)])
            .to_list()
        )
        refs = await SourceRefEntity.find(
            {"resource_id": resource_id, "content_revision": content_revision}
        ).to_list()
        return GraphBuildSource(
            resource_id=resource_id,
            content_revision=content_revision,
            structure_mode=revision.structure_mode,
            markdown=_assemble_source_text(parts, [full_span]),
            sections=[_to_section(entity) for entity in sections],
            reading_blocks=[_to_reading_block(entity) for entity in blocks],
            source_refs=[_to_source_ref(entity) for entity in refs],
        )

    async def _get_sections_for_revision(
        self,
        resource_id: str,
        content_revision: str,
    ) -> list[Section]:
        entities = (
            await SectionEntity.find(
                {
                    "resource_id": resource_id,
                    "content_revision": content_revision,
                }
            )
            .sort("+own_start")
            .to_list()
        )
        return [_to_section(entity) for entity in entities]

    async def _get_parts(
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
        return [_to_source_part(entity) for entity in entities]

    @staticmethod
    def _require_revision(
        revision: ContentRevision,
        content_revision: str,
    ) -> None:
        if revision.content_revision != content_revision:
            raise PublishedResourceRevisionError(
                f"content revision {content_revision} is not published for "
                f"{revision.resource_id}"
            )


def _assemble_source_text(
    parts: Sequence[SourcePart],
    source_spans: Sequence[SourceSpan],
) -> str:
    """拼接 Python 字符 span，并拒绝缺失、重叠或损坏的存储分片。"""
    if not source_spans:
        return ""
    ordered_parts = sorted(parts, key=lambda part: part.source_span.start_offset)
    revision = ordered_parts[0].content_revision if ordered_parts else "unknown"
    _validate_parts(ordered_parts, revision)

    fragments: list[str] = []
    for span in source_spans:
        cursor = span.start_offset
        span_fragments: list[str] = []
        for part in ordered_parts:
            part_start = part.source_span.start_offset
            part_end = part.source_span.end_offset
            if part_end <= cursor:
                continue
            if part_start >= span.end_offset:
                break
            if part_start > cursor:
                raise PublishedResourceCorruptError(
                    f"content revision {revision} source parts have a gap"
                )
            fragment_end = min(part_end, span.end_offset)
            span_fragments.append(
                part.text[cursor - part_start : fragment_end - part_start]
            )
            cursor = fragment_end
            if cursor == span.end_offset:
                break
        if cursor != span.end_offset:
            raise PublishedResourceCorruptError(
                f"content revision {revision} source parts do not cover span"
            )
        fragments.append("".join(span_fragments))
    return "\n\n".join(fragments)


def _validate_parts(parts: Sequence[SourcePart], content_revision: str) -> None:
    previous_end = None
    for part in parts:
        start = part.source_span.start_offset
        end = part.source_span.end_offset
        if end - start != len(part.text):
            raise PublishedResourceCorruptError(
                f"content revision {content_revision} has an invalid source part"
            )
        if previous_end is not None and start < previous_end:
            raise PublishedResourceCorruptError(
                f"content revision {content_revision} source parts overlap"
            )
        previous_end = end


def _to_content_revision(record: ContentRevisionEntity) -> ContentRevision:
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
        anchors=[
            DocumentAnchor(
                label=anchor.label,
                source_span=SourceSpan(anchor.start_offset, anchor.end_offset),
            )
            for anchor in record.anchors
        ],
    )


def _to_source_part(record: SourcePartEntity) -> SourcePart:
    return SourcePart(
        resource_id=record.resource_id,
        content_revision=record.content_revision,
        part_index=record.part_index,
        source_span=SourceSpan(record.start_offset, record.end_offset),
        text=record.text,
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


def _overlaps(left: SourceSpan, right: SourceSpan) -> bool:
    return left.start_offset < right.end_offset and right.start_offset < left.end_offset


def _overlapping_labels(
    source_spans: Sequence[SourceSpan],
    labeled_ranges: Sequence[PageRange | DocumentAnchor],
) -> list[str]:
    """按文档顺序投影页码或锚点标签，空正文不制造归属信息。"""
    return list(
        dict.fromkeys(
            item.page_label if isinstance(item, PageRange) else item.label
            for item in labeled_ranges
            if any(_overlaps(span, item.source_span) for span in source_spans)
        )
    )
