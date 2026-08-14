"""编排一个资源 revision 的构建与跨后端发布。

``ResourceIndexer`` 是 INDEX 流水线的顶层入口：把一份权威 Markdown 同时落库到
三个后端（资源元数据 / 检索索引 / 知识图谱），并保证它们属于同一个 ``content_revision``，
从而支持检索命中后回源、回章节、回图谱。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rag.application.rag.acl import ResourceAclRefresher
from rag.domain.models.structure import StructureMode
from rag.domain.repositories import (
    KnowledgeGraphRepository,
    ResourceAclStore,
    ResourceIndexWriter,
    RetrievalIndexWriter,
    StageAction,
)

from .constructor import (
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
from .graph import KnowledgeGraphExtractor

if TYPE_CHECKING:
    from rag.utils.llm_clients import EmbeddingClient


class ResourceIndexer:
    """把权威 Markdown 发布为可读、可检索、可探索的同一 revision。

    设计要点：
    - 派生身份全部由 ``content_revision`` 派生，重复索引同一内容会得到完全一致的 ID，
      支持增量复用与缓存命中。
    - 写入流程分阶段（stage → apply → activate → cleanup），中途失败不会污染线上版本。
    - 检索索引与知识图谱解耦：FLAT_TEXT/EMPTY 不抽取图谱，但仍会发布检索索引。
    """

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
        graph_repository: KnowledgeGraphRepository,
    ) -> None:
        self._contextual_text = contextual_text
        self._embedding_client = embedding_client
        self._acl_refresher = acl_refresher
        self._acl_reader = acl_reader
        self._resource_writer = resource_writer
        self._retrieval_writer = retrieval_writer
        self._graph_extractor = graph_extractor
        self._graph_repository = graph_repository

    async def index_resource(
        self,
        *,
        resource_id: str,
        document_version: int,
        markdown: str,
    ) -> StageAction:
        """对一份权威 Markdown 执行完整的索引构建与发布。

        流程：
        1. 派生 revision / structure / sections / reading_blocks / chunks / source_refs，
           全部基于权威 markdown 计算，身份确定。
        2. ``stage_revision`` 把派生产物落库到“暂存区”，返回 ``StageAction``：
           - ``STALE`` 表示该 revision 已存在且未变化，可直接跳过昂贵步骤；
           - ``APPLIED`` 表示新建或覆盖，需要继续后续发布流程。
        3. 上下文增强 + ACL 同步 + 向量计算 + 检索索引发布（activate）。
        4. 仅对 SECTIONED 文档抽取并发布知识图谱；其它模式调用 ``skip`` 释放锁。
        5. 清理旧 revision，使线上只保留最新版本。
        """
        # 1. 派生身份与结构
        # 先用 markdown 计算 content_revision（不依赖 structure），供后续派生 ID 使用。
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
        # FLAT_TEXT 模式没有 Section 树，需要单独按 4000 字符切分；其它模式直接复用 structure。
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

        # 2. 资源元数据暂存
        # STALE 表示该 revision 与已上线版本完全一致，跳过昂贵的下游步骤。
        action = await self._resource_writer.stage_revision(
            revision,
            markdown,
            sections,
            reading_blocks,
            source_refs,
        )
        if action is StageAction.STALE:
            return action

        # 3. 上下文增强
        # 为每个 chunk 生成检索上下文，提升 dense/BM25 召回；已缓存的内容不会重复调用模型。
        chunks = await self._contextual_text.contextualize(
            resource_id=resource_id,
            structure=structure,
            reading_blocks=reading_blocks,
            chunks=chunks,
        )

        # 4. 向量计算
        # 先尝试复用已存储的向量（chunk_id 一致即可复用），缺失部分才调用 embedding 模型。
        dense_vectors = dict(
            await self._retrieval_writer.load_reusable_vectors(
                resource_id=resource_id,
                chunks=chunks,
            )
        )
        missing_chunks = [
            chunk for chunk in chunks if chunk.chunk_id not in dense_vectors
        ]
        if missing_chunks:
            result = await self._embedding_client.aembed(
                [chunk.index_text for chunk in missing_chunks]
            )
            # 防御：保证 embedding 数量与输入一致，避免向量与 chunk 错位。
            if len(result.embeddings) != len(missing_chunks):
                raise ValueError(
                    "embedding response count does not match retrieval chunks"
                )
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

        # 5. ACL 同步
        # 检索结果必须按 ACL 过滤；若资源尚无 ACL 则视为配置错误，直接报错。
        # 显式刷新 ACL，避免在索引期间资源 ACL 发生变更导致检索结果不一致。
        await self._acl_refresher.refresh(resource_id)
        resource_acl = await self._acl_reader.get_resource_acl(resource_id)
        if resource_acl is None:
            raise RuntimeError(f"resource {resource_id} has no synchronized ACL")

        # 6. 检索索引发布
        # write_staged_revision 写入暂存；apply_revision + activate_revision 才让线上可见。
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
        # 清理检索后端的旧 revision，避免历史版本累积。
        await self._retrieval_writer.delete_other_revisions(
            resource_id=resource_id,
            keep_content_revision=content_revision,
        )

        # 7. 知识图谱发布
        # 仅 SECTIONED 文档具备抽取图谱所需的章节上下文；其它模式显式 skip 以释放占用。
        if structure.mode is StructureMode.SECTIONED:
            await self._graph_repository.begin_build(
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
            await self._graph_repository.publish(
                graph=graph,
                document_version=document_version,
            )
        else:
            await self._graph_repository.skip(
                resource_id=resource_id,
                content_revision=content_revision,
                document_version=document_version,
            )

        # 8. 资源元数据清理
        # 资源后端也清理旧 revision，使线上资源元数据只保留最新版本。
        await self._resource_writer.delete_other_revisions(
            resource_id=resource_id,
            keep_content_revision=content_revision,
        )
        return action
