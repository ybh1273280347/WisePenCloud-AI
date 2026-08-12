"""编排一个资源 revision 的构建与跨后端发布。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rag.application.rag.acl import ResourceAclRefresher
from rag.domain.document_structure import StructureMode
from rag.domain.repositories import (
    KnowledgeGraphWriter,
    ResourceAclStore,
    ResourceIndexWriter,
    RetrievalIndexWriter,
    StageAction,
)

from .builders import (
    build_content_revision_id,
    build_flat_text_sections,
    build_reading_blocks,
    build_retrieval_chunks,
    build_source_refs,
    create_content_revision,
    merge_candidate_graph,
    parse_document_structure,
)
from .contextualize import ContextualTextIndexer
from .graph_extraction import KnowledgeGraphExtractor

if TYPE_CHECKING:
    from rag.utils.llm_clients import EmbeddingClient


class ResourceIndexer:
    """把权威 Markdown 发布为可读、可检索、可探索的同一 revision。"""

    def __init__(
        self,
        *,
        contextual_text: ContextualTextIndexer,
        embedding_client: EmbeddingClient,
        acl_refresher: ResourceAclRefresher,
        acl_reader: ResourceAclStore,
        resource_writer: ResourceIndexWriter,
        retrieval_writer: RetrievalIndexWriter,
        graph_extractor: KnowledgeGraphExtractor,
        graph_writer: KnowledgeGraphWriter,
    ) -> None:
        self._contextual_text = contextual_text
        self._embedding_client = embedding_client
        self._acl_refresher = acl_refresher
        self._acl_reader = acl_reader
        self._resource_writer = resource_writer
        self._retrieval_writer = retrieval_writer
        self._graph_extractor = graph_extractor
        self._graph_writer = graph_writer

    async def index_resource(
        self,
        *,
        resource_id: str,
        document_version: int,
        markdown: str,
    ) -> StageAction:
        content_revision = build_content_revision_id(
            resource_id=resource_id,
            document_version=document_version,
            markdown=markdown,
        )
        structure = parse_document_structure(
            resource_id=resource_id,
            content_revision=content_revision,
            markdown=markdown,
        )
        revision = create_content_revision(
            resource_id=resource_id,
            document_version=document_version,
            markdown=markdown,
            structure=structure,
        )
        sections = (
            build_flat_text_sections(
                resource_id=resource_id,
                content_revision=content_revision,
                markdown=markdown,
            )
            if structure.mode is StructureMode.FLAT_TEXT
            else structure.sections
        )
        structure.sections = sections
        reading_blocks = build_reading_blocks(
            resource_id=resource_id,
            content_revision=content_revision,
            markdown=markdown,
            structure=structure,
            sections=sections,
        )
        chunks = build_retrieval_chunks(
            resource_id=resource_id,
            content_revision=content_revision,
            markdown=markdown,
            structure=structure,
            sections=sections,
            reading_blocks=reading_blocks,
        )
        source_refs = build_source_refs(
            resource_id=resource_id,
            content_revision=content_revision,
            markdown=markdown,
            structure=structure,
            sections=sections,
            reading_blocks=reading_blocks,
            retrieval_chunks=chunks,
        )
        action = await self._resource_writer.stage_revision(
            revision,
            markdown,
            sections,
            reading_blocks,
            source_refs,
        )
        if action is StageAction.STALE:
            return action

        chunks = await self._contextual_text.contextualize(
            resource_id=resource_id,
            structure=structure,
            reading_blocks=reading_blocks,
            chunks=chunks,
        )
        await self._acl_refresher.refresh(resource_id)
        resource_acl = (await self._acl_reader.get_resource_acls([resource_id])).get(
            resource_id
        )
        if resource_acl is None:
            raise RuntimeError(f"resource {resource_id} has no synchronized ACL")

        dense_vectors = dict(
            await self._retrieval_writer.load_reusable_vectors(
                resource_id=resource_id,
                chunks=chunks,
            )
        )
        missing_chunks = [chunk for chunk in chunks if chunk.chunk_id not in dense_vectors]
        if missing_chunks:
            result = await self._embedding_client.aembed(
                [chunk.index_text for chunk in missing_chunks]
            )
            if len(result.embeddings) != len(missing_chunks):
                raise ValueError("embedding response count does not match retrieval chunks")
            dense_vectors.update(
                {
                    chunk.chunk_id: vector
                    for chunk, vector in zip(
                        missing_chunks,
                        result.embeddings,
                        strict=True,
                    )
                }
            )

        await self._retrieval_writer.write_staged_revision(
            resource_id=resource_id,
            content_revision=content_revision,
            chunks=chunks,
            source_refs=source_refs,
            dense_vectors=dense_vectors,
            resource_acl=resource_acl,
        )
        await self._resource_writer.apply_revision(revision)
        await self._retrieval_writer.activate_revision(
            resource_id=resource_id,
            content_revision=content_revision,
        )
        await self._retrieval_writer.delete_other_revisions(
            resource_id=resource_id,
            keep_content_revision=content_revision,
        )

        if structure.mode is StructureMode.SECTIONED:
            await self._graph_writer.begin_build(
                resource_id=resource_id,
                content_revision=content_revision,
                document_version=document_version,
            )
            graph = merge_candidate_graph(
                resource_id=resource_id,
                content_revision=content_revision,
                extractions=await self._graph_extractor.extract(
                    resource_id=resource_id,
                    content_revision=content_revision,
                ),
            )
            await self._graph_writer.publish(
                graph=graph,
                document_version=document_version,
            )
        else:
            await self._graph_writer.skip(
                resource_id=resource_id,
                content_revision=content_revision,
                document_version=document_version,
            )

        await self._resource_writer.delete_other_revisions(
            resource_id=resource_id,
            keep_content_revision=content_revision,
        )
        return action
