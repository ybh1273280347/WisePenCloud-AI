from __future__ import annotations

from typing import Any

from neo4j import Driver
from neo4j_graphrag.experimental.components.entity_relation_extractor import (
    LLMEntityRelationExtractor,
    OnError,
)
from neo4j_graphrag.experimental.components.kg_writer import Neo4jWriter
from neo4j_graphrag.experimental.components.types import (
    DocumentInfo,
    LexicalGraphConfig,
    TextChunk,
    TextChunks,
)

from chat.application.rag.graph.graphrag_llm import WisePenGraphRagLLM
from chat.application.utils.llm_clients import QueryClient

_DOCUMENT_NODE_LABEL = "RagDocument"
_CHUNK_NODE_LABEL = "RagChunk"
_CHUNK_TO_DOCUMENT_RELATIONSHIP = "FROM_DOCUMENT"
_NEXT_CHUNK_RELATIONSHIP = "NEXT_CHUNK"
_ENTITY_TO_CHUNK_RELATIONSHIP = "FROM_CHUNK"


class Neo4jGraphRagKnowledgeGraphBuilder:
    """使用 neo4j-graphrag 组件构建 evidence-backed KG。"""

    __slots__ = (
        "_driver",
        "_extractor",
        "_lexical_graph_config",
        "_neo4j_database",
        "_writer",
    )

    def __init__(
            self,
            *,
            driver: Driver | None,
            llm_client: QueryClient,
            neo4j_database: str | None = None,
    ) -> None:
        self._driver = driver
        self._neo4j_database = neo4j_database or None
        # neo4j-graphrag 这些类型是 Pydantic 模型，用 model_validate 贴近 SDK 真实运行边界。
        self._lexical_graph_config = LexicalGraphConfig.model_validate(
            {
                "document_node_label": _DOCUMENT_NODE_LABEL,
                "chunk_node_label": _CHUNK_NODE_LABEL,
                "chunk_to_document_relationship_type": _CHUNK_TO_DOCUMENT_RELATIONSHIP,
                "next_chunk_relationship_type": _NEXT_CHUNK_RELATIONSHIP,
                "node_to_chunk_relationship_type": _ENTITY_TO_CHUNK_RELATIONSHIP,
                "chunk_id_property": "chunk_id",
                "chunk_index_property": "chunk_index",
                "chunk_text_property": "evidence_text",
                "chunk_embedding_property": "embedding",
            }
        )
        if driver is None:
            self._extractor = None
            self._writer = None
            return

        # Neo4jWriter 初始化会读取 driver 状态，因此只在 driver 存在时构造 SDK 组件。
        self._extractor = LLMEntityRelationExtractor(
            llm=WisePenGraphRagLLM(llm_client),
            create_lexical_graph=True,
            on_error=OnError.IGNORE,
            use_structured_output=True,
        )
        self._writer = Neo4jWriter(
            driver=driver,
            neo4j_database=self._neo4j_database,
            clean_db=True,
        )

    async def upsert_document_graph(
            self,
            *,
            parent_chunks: tuple[Any, ...],
            child_chunks: tuple[Any, ...],
            dense_vectors: dict[str, list[float]],
            resource_id: str,
            document_version: str,
            corpus_version: str,
    ) -> None:
        if self._driver is None or self._extractor is None or self._writer is None:
            return
        if not child_chunks:
            return

        graph = await self._extractor.run(
            chunks=_build_text_chunks(
                child_chunks=child_chunks,
                dense_vectors=dense_vectors,
                resource_id=resource_id,
                document_version=document_version,
                corpus_version=corpus_version,
                parent_text_by_id={
                    parent.chunk_id: parent.text
                    for parent in parent_chunks
                },
            ),
            document_info=DocumentInfo.model_validate(
                {
                    "path": resource_id,
                    "uid": f"{resource_id}:{document_version}",
                    "metadata": {
                        "resource_id": resource_id,
                        "document_version": document_version,
                        "corpus_version": corpus_version,
                    },
                },
            ),
            lexical_graph_config=self._lexical_graph_config,
        )
        await self._writer.run(
            graph=graph,
            lexical_graph_config=self._lexical_graph_config,
        )

def _build_text_chunks(
        *,
        child_chunks: tuple[Any, ...],
        dense_vectors: dict[str, list[float]],
        resource_id: str,
        document_version: str,
        corpus_version: str,
        parent_text_by_id: dict[str, str],
) -> TextChunks:
    # KG 构建使用 evidence text 和 chunk 元数据，版本字段只作为投影标识保留。
    return TextChunks.model_validate(
        {
            "chunks": [
                {
                    "text": child.indexing_text or child.text,
                    "index": child.chunk_index,
                    "uid": child.chunk_id,
                    "metadata": {
                        "chunk_id": child.chunk_id,
                        "parent_chunk_id": child.parent_chunk_id,
                        "parent_text": parent_text_by_id.get(child.parent_chunk_id, ""),
                        "resource_id": resource_id,
                        "document_version": document_version,
                        "corpus_version": corpus_version,
                        "page_label": child.page_label,
                        "section_path": list(child.section_path),
                        "anchor_labels": list(child.anchor_labels),
                        "embedding": dense_vectors.get(child.chunk_id, []),
                    },
                }
                for child in child_chunks
            ]
        }
    )
