# RAG 核心实现蓝图

本文把 RAG 定稿方案落成后续开发可直接对照的实现骨架。这里写的是伪代码和模块联动，不是当前必须立即提交的生产代码。

当前边界：

- 可以明确 Qdrant、Elasticsearch、Neo4j、缓存和 Context Builder 的主流程。
- 可以明确入库 chunk 如何携带 `extra_indexes`，以及后续如何通过页码、章节、锚点精确定位证据。
- 不定义 ACL 字段、不定义权限 filter 数据结构、不实现授权证据缓存模型。权限模型确定后，只在本文标出的 filter / cache key
  插槽接入。

## 1. 总链路

```text
Kafka ingestion event
  -> RagMarkdownIngestionPayload
  -> RagChunkingService
  -> ContextIndexingService
  -> Corpus Store(parent_chunks / child_chunks / extra_indexes)
  -> Qdrant child chunk dense + sparse index
  -> Elasticsearch strict keyword / locator index
  -> Neo4j evidence-backed concept graph
  -> bump corpus_version / projection_epoch

knowledge_search
  -> optional Elasticsearch strict prefilter
  -> Qdrant dense + sparse retrieval
  -> RagEvidenceRankingService
  -> AnswerabilityHardGate
  -> AnswerabilitySoftGate
  -> optional Neo4j ontology enhancement
  -> evidence materialization
  -> Context Builder
  -> main model
```

关键原则：

- Qdrant 是主召回源，负责 dense + sparse/BM25。
- Elasticsearch 只做严格关键词、标题、页码、锚点等前置范围过滤，不作为默认第二召回 lane。
- Neo4j 只在 Soft Gate 有 warning 后做后置增强，不混入 direct topK。
- Corpus Store 是 chunk 原文、父子关系、`extra_indexes` 的事实源。
- 缓存只缓存可校验中间事实，不缓存 final answer。

## 2. 入库写入边界

当前入库协议以 [INGESTION_PROTOCOL.md](INGESTION_PROTOCOL.md) 为准。核心输入是已经注入页码标记的 Markdown：

```python
payload = RagMarkdownIngestionPayload(
    resource_id=event.resource_id,
    document_id=event.document_id,
    document_version=event.document_version,
    markdown=event.markdown_with_page_markers,
    title=event.title,
)
```

ACL 即使由上游提供，也不进入当前 `RagMarkdownIngestionPayload`；后续权限模型确定后由独立边界处理。

### 2.1 Chunking 与 extra index 投影

`chunking_engine` 产出 chunk 和 `ChunkIndex`，RAG 入库把页码、章节、锚点索引投影到 chunk 自身：

```python
chunking_result = rag_chunking_service.chunk_payload(payload)

for child in chunking_result.child_chunks:
    assert child.extra_indexes
    # child.extra_indexes 是证据定位事实源，不再写 extra_index_names 这种影子字段。
```

`extra_indexes` 的稳定语义：

| 字段                            | 语义                                                                        |
|-------------------------------|---------------------------------------------------------------------------|
| `index_name`                  | chunking engine 的完整索引名，例如 `page:3`、`section:鉴权 > Token`、`anchor:Table 1`。 |
| `index_kind`                  | `PAGE` / `SECTION` / `ANCHOR`。                                            |
| `page_label`                  | 页码标签，只在 `PAGE` 索引上有值。                                                     |
| `section_path`                | 章节路径，只在 `SECTION` 索引上有值。                                                  |
| `anchor_label`                | 表格、图片、公式等锚点标签，只在 `ANCHOR` 索引上有值。                                          |
| `start_offset` / `end_offset` | 索引覆盖的 Markdown 原文字符偏移。                                                    |

chunking engine 已保证 chunk 不跨页，所以不写 `page_range` / `page_numbers`。需要页码时，从 `extra_indexes` 中取
`index_kind == PAGE` 的 `page_label`。

### 2.2 Corpus Store

Corpus Store 保存可回源的事实数据，后续 Qdrant、Elastic、Neo4j 都只保存检索所需投影。

```python
class RagCorpusRepository:
    async def upsert_document(
        self,
        *,
        resource_id: str,
        document_id: str,
        document_version: str,
        title: str,
        parent_chunks: tuple[RagParentChunk, ...],
        child_chunks: tuple[RagChildChunk, ...],
    ) -> None:
        ...

    async def load_child_chunks(
        self,
        chunk_ids: tuple[str, ...],
    ) -> tuple[RagChildChunk, ...]:
        ...

    async def load_parent_chunks(
        self,
        chunk_ids: tuple[str, ...],
    ) -> tuple[RagParentChunk, ...]:
        ...

    async def find_children_by_locator(
        self,
        *,
        document_id: str,
        page_label: str | None = None,
        anchor_label: str | None = None,
        section_path: tuple[str, ...] = (),
    ) -> tuple[RagChildChunk, ...]:
        ...
```

Corpus Store 查询可以直接基于 `extra_indexes` 做精确定位；如果底层数据库不适合查嵌套数组，可以额外维护派生查询字段，但派生字段不是入库协议。

### 2.3 Qdrant 写入

Qdrant 以 child chunk 为检索单位。写入文本使用 `indexing_text`，证据引用仍回到 `text`。

```python
class RagQdrantRepository:
    async def upsert_child_chunks(
        self,
        *,
        child_chunks: tuple[RagChildChunk, ...],
        dense_vectors: dict[str, list[float]],
        sparse_vectors: dict[str, SparseVector],
        resource_id: str,
        document_id: str,
        document_version: str,
        corpus_version: str,
    ) -> None:
        points = [
            QdrantPoint(
                id=child.chunk_id,
                dense_vector=dense_vectors[child.chunk_id],
                sparse_vector=sparse_vectors[child.chunk_id],
                payload={
                    "chunk_id": child.chunk_id,
                    "parent_chunk_id": child.parent_chunk_id,
                    "resource_id": resource_id,
                    "document_id": document_id,
                    "document_version": document_version,
                    "corpus_version": corpus_version,
                    "content_hash": child.content_hash,
                    "page_label": child.page_label,
                    "section_path": list(child.section_path),
                    "anchor_labels": list(child.anchor_labels),
                },
            )
            for child in child_chunks
        ]
        await self._client.upsert(points)
```

注意：

- Qdrant payload 中的 `page_label`、`section_path`、`anchor_labels` 是从 `extra_indexes` 派生的检索投影，方便 filter，不是新的
  chunk 协议字段。
- 不把完整 `extra_indexes` 当作 Qdrant 的事实源；完整结构仍在 Corpus Store。
- 权限过滤位置在 Qdrant filter 组合处，当前不定义 filter 形状。

### 2.4 Elasticsearch 写入

Elastic 只服务 strict keyword prefilter 和精准 locator 查询。它可以保存 `indexing_text`、标题、章节、页码、锚点等
keyword/text 字段。

```python
class RagElasticRepository:
    async def upsert_child_chunks(
        self,
        *,
        child_chunks: tuple[RagChildChunk, ...],
        resource_id: str,
        document_id: str,
        document_version: str,
        corpus_version: str,
        title: str,
    ) -> None:
        docs = [
            {
                "_id": child.chunk_id,
                "chunk_id": child.chunk_id,
                "parent_chunk_id": child.parent_chunk_id,
                "resource_id": resource_id,
                "document_id": document_id,
                "document_version": document_version,
                "corpus_version": corpus_version,
                "title": title,
                "indexing_text": child.indexing_text,
                "evidence_text": child.text,
                "page_label": child.page_label,
                "section_path": list(child.section_path),
                "section_path_text": " > ".join(child.section_path),
                "anchor_labels": list(child.anchor_labels),
            }
            for child in child_chunks
        ]
        await self._bulk_upsert(docs)
```

Elastic 查询只返回候选范围：

```python
class RagElasticRepository:
    async def strict_prefilter(
        self,
        *,
        query: str,
        resource_id: str,
        corpus_version: str,
        locator: EvidenceLocatorQuery | None = None,
        limit: int = 1000,
    ) -> tuple[str, ...]:
        elastic_filter = {
            "resource_id": resource_id,
            "corpus_version": corpus_version,
            # permission filter slot: 权限模型确定后在这里追加，不在当前协议中定义。
        }

        if locator and locator.page_label:
            elastic_filter["page_label"] = locator.page_label
        if locator and locator.anchor_label:
            elastic_filter["anchor_labels"] = locator.anchor_label
        if locator and locator.section_path:
            elastic_filter["section_path"] = list(locator.section_path)

        return await self._search_chunk_ids(
            query=query,
            filter=elastic_filter,
            limit=limit,
        )
```

## 3. 入库编排伪代码

```python
class RagIngestionApplicationService:
    async def ingest_markdown(self, payload: RagMarkdownIngestionPayload) -> None:
        content_hash = hash_text(payload.markdown)

        cached = await self._ingestion_cache.get_chunking_result(
            document_id=payload.document_id,
            document_version=payload.document_version,
            content_hash=content_hash,
            pipeline_name="nested_markdown",
            pipeline_version=self._chunking_pipeline_version,
        )
        if cached:
            chunking_result = cached
        else:
            chunking_result = self._chunking_service.chunk_payload(payload)
            await self._ingestion_cache.put_chunking_result(...)

        child_chunks = await self._context_indexing_service.build(
            child_chunks=chunking_result.child_chunks,
            parent_chunks=chunking_result.parent_chunks,
            document_title=payload.title,
        )

        dense_vectors = await self._embedding_service.embed(
            {child.chunk_id: child.indexing_text for child in child_chunks}
        )
        sparse_vectors = await self._sparse_encoder.encode(
            {child.chunk_id: child.indexing_text for child in child_chunks}
        )

        corpus_version = await self._corpus_versions.next_version(
            resource_id=payload.resource_id,
            document_id=payload.document_id,
            document_version=payload.document_version,
        )

        await self._corpus.upsert_document(
            resource_id=payload.resource_id,
            document_id=payload.document_id,
            document_version=payload.document_version,
            title=payload.title,
            parent_chunks=chunking_result.parent_chunks,
            child_chunks=child_chunks,
        )
        await self._qdrant.upsert_child_chunks(...)
        await self._elastic.upsert_child_chunks(...)
        await self._neo4j.upsert_concept_graph(...)

        await self._corpus_versions.publish(
            resource_id=payload.resource_id,
            corpus_version=corpus_version,
        )
```

入库缓存只基于内容、文档版本和处理配置，不基于权限。权限变化不应要求重新分块、重新生成 embedding 或重新抽图；后续只更新权限投影和检索
filter。

## 4. 检索编排伪代码

```python
class KnowledgeSearchApplicationService:
    async def search(self, request: KnowledgeSearchRequest) -> KnowledgeSearchResult:
        corpus_version = await self._corpus_versions.resolve(
            resource_id=request.resource_id,
        )

        locator = self._locator_parser.parse(request.query)
        candidate_scope = None
        if self._should_use_elastic_prefilter(request, locator):
            candidate_scope = await self._elastic.strict_prefilter(
                query=request.query,
                resource_id=request.resource_id,
                corpus_version=corpus_version,
                locator=locator,
            )

        retrieved = await self._qdrant.retrieve(
            query=request.query,
            resource_id=request.resource_id,
            corpus_version=corpus_version,
            candidate_chunk_ids=candidate_scope,
            retrieval_profile=request.retrieval_profile,
            top_k=request.candidate_limit,
            # permission filter slot: 权限模型确定后在 Qdrant filter 中追加。
        )

        ranked = await self._ranking.rank(
            RagEvidenceRankingRequest(
                query=request.query,
                chunks=retrieved,
                top_k=request.top_k,
                candidate_limit=request.candidate_limit,
            )
        )

        answerability_input = RagAnswerabilityInput(
            query=request.query,
            retrieval_profile=request.retrieval_profile,
            ranked=ranked.ranked,
        )
        hard_gate = self._hard_gate.decide(answerability_input)
        if not hard_gate.should_continue:
            return KnowledgeSearchResult.rejected(hard_gate)

        direct_evidence = await self._evidence_materializer.materialize_ranked(
            ranked.ranked,
            resource_id=request.resource_id,
            corpus_version=corpus_version,
            request_scope=request.scope,
        )

        soft_warning = await self._soft_gate.evaluate(answerability_input)

        graph_evidence = ()
        ontology_hints = ()
        if soft_warning.should_enhance_with_neo4j:
            graph_result = await self._graph_enhancer.enhance(
                query=request.query,
                direct_evidence=direct_evidence,
                warnings=soft_warning.warnings,
                resource_id=request.resource_id,
                corpus_version=corpus_version,
                request_scope=request.scope,
            )
            graph_evidence = await self._evidence_materializer.materialize_graph(
                graph_result.graph_evidence_ids,
                resource_id=request.resource_id,
                corpus_version=corpus_version,
                request_scope=request.scope,
            )
            ontology_hints = graph_result.ontology_hints

        context = self._context_builder.build(
            query=request.query,
            direct_evidence=direct_evidence,
            graph_evidence=graph_evidence,
            ontology_hints=ontology_hints,
            answerability_warning=soft_warning,
        )
        return KnowledgeSearchResult.ready(context)
```

`AnswerabilitySoftGate` 当前 prompt 读取 `RankedCandidate.candidate.text`。因此 retrieval 阶段要给 ranking 候选带上足够的
child evidence text；materialization 阶段再补 parent context、citation、locator 等完整上下文。

## 5. Qdrant 主召回

Qdrant 查询同时走 dense 和 sparse/BM25，返回 child chunk 候选。

```python
class RagQdrantRepository:
    async def retrieve(
        self,
        *,
        query: str,
        resource_id: str,
        corpus_version: str,
        candidate_chunk_ids: tuple[str, ...] | None,
        retrieval_profile: RagRetrievalProfile,
        top_k: int,
    ) -> tuple[ScoredChunk, ...]:
        dense_vector = await self._embedding.embed_query(query)
        sparse_vector = await self._sparse_encoder.encode_query(query)

        qdrant_filter = {
            "resource_id": resource_id,
            "corpus_version": corpus_version,
        }
        if candidate_chunk_ids is not None:
            qdrant_filter["chunk_id"] = {"in": candidate_chunk_ids}

        # permission filter slot: 权限模型确定后追加到 qdrant_filter。

        dense_hits, sparse_hits = await gather(
            self._search_dense(dense_vector, qdrant_filter, top_k),
            self._search_sparse(sparse_vector, qdrant_filter, top_k),
        )

        merged = reciprocal_rank_fusion(
            dense_hits=dense_hits,
            sparse_hits=sparse_hits,
            profile=retrieval_profile,
        )
        return tuple(
            ScoredChunk(
                chunk_id=hit.chunk_id,
                text=hit.payload["evidence_text"],
                retrieval_score=hit.score,
                retrieval_rank=rank,
                group_key=hit.payload["parent_chunk_id"],
            )
            for rank, hit in enumerate(merged[:top_k], start=1)
        )
```

如果 Qdrant payload 不保存 `evidence_text`，这里应批量回源 child chunks 填充 `ScoredChunk.text`。为了 Soft Gate 和 rerank
成本，建议 payload 可以保存短 child text，但最终引用仍以 Corpus Store 为准。

## 6. Elastic strict prefilter

Elastic 触发条件应该保守，只在查询中出现明确精确约束时启用：

- 用户指定标题、文件名、编号、代码标识符。
- 用户指定页码，例如“第 12 页”。
- 用户指定锚点，例如“表 3”“Figure 2”“公式 1”。
- `RagRetrievalProfile.ANCHORED_EXACT`。

```python
def should_use_elastic_prefilter(
    *,
    query: str,
    retrieval_profile: RagRetrievalProfile,
    locator: EvidenceLocatorQuery | None,
) -> bool:
    return bool(
        retrieval_profile == RagRetrievalProfile.ANCHORED_EXACT
        or locator
        or looks_like_code_identifier_query(query)
        or contains_required_keyword_operator(query)
    )
```

Elastic 输出只是一组 `candidate_chunk_ids`。Qdrant 仍然在这个 scope 内做 dense + sparse 主召回。

## 7. 精准 page / anchor / section 定位

当用户或上层工具明确要求“定位某一页、某个表、某个锚点及其上下文”时，不需要先走自然语言主召回，可以直接走 locator 查询。

```python
@dataclass(frozen=True, slots=True)
class EvidenceLocatorQuery:
    document_id: str
    page_label: str | None = None
    anchor_label: str | None = None
    section_path: tuple[str, ...] = ()
    context_window_children: int = 2
```

定位流程：

```python
class EvidenceLocatorService:
    async def locate(self, query: EvidenceLocatorQuery) -> EvidenceLocatorResult:
        child_chunks = await self._corpus.find_children_by_locator(
            document_id=query.document_id,
            page_label=query.page_label,
            anchor_label=query.anchor_label,
            section_path=query.section_path,
        )

        if not child_chunks:
            candidate_ids = await self._elastic.strict_prefilter(
                query="",
                resource_id=self._resource_id,
                corpus_version=self._corpus_version,
                locator=query,
            )
            child_chunks = await self._corpus.load_child_chunks(candidate_ids)

        focused = choose_best_locator_matches(
            child_chunks=child_chunks,
            page_label=query.page_label,
            anchor_label=query.anchor_label,
            section_path=query.section_path,
        )

        parent_ids = tuple(dict.fromkeys(child.parent_chunk_id for child in focused))
        parent_chunks = await self._corpus.load_parent_chunks(parent_ids)
        sibling_context = await self._corpus.load_sibling_children(
            focused,
            window=query.context_window_children,
        )

        return EvidenceLocatorResult(
            focused_children=focused,
            parent_chunks=parent_chunks,
            sibling_context=sibling_context,
        )
```

精确定位的上下文优先级：

1. 命中的 child chunk 原文。
2. 同 `parent_chunk_id` 的父块上下文。
3. 同页 `page_label` 附近的 sibling child chunks。
4. 同 `section_path` 的相邻 child chunks。

由于 chunk 不跨页，`page_label` 命中后可以确定 child chunk 属于该页；如果需要“整页上下文”，加载所有带同一 `page_label` 的
child chunks 即可。

## 8. Neo4j 图增强

Neo4j 保存 evidence-backed concept graph。它不替代 Qdrant 文本召回。

### 8.1 图入库

```python
class RagNeo4jRepository:
    async def upsert_concept_graph(
        self,
        *,
        resource_id: str,
        document_id: str,
        document_version: str,
        corpus_version: str,
        child_chunks: tuple[RagChildChunk, ...],
    ) -> None:
        for child in child_chunks:
            await self._merge_chunk_node(
                chunk_id=child.chunk_id,
                parent_chunk_id=child.parent_chunk_id,
                resource_id=resource_id,
                document_id=document_id,
                document_version=document_version,
                corpus_version=corpus_version,
                evidence_text=child.text,
                indexing_text=child.indexing_text,
                page_label=child.page_label,
                section_path=child.section_path,
                anchor_labels=child.anchor_labels,
                start_offset=child.start_offset,
                end_offset=child.end_offset,
            )

        extraction = await self._graph_extraction.extract(
            chunks=child_chunks,
            ontology_schema_version=self._ontology_schema_version,
        )
        await self._merge_mentions_concepts_relations(extraction)
```

图节点以 child chunk 为证据锚点：

```text
(:Chunk)-[:HAS_MENTION]->(:Mention)-[:REFERS_TO]->(:Concept)
(:RelationEvidence)-[:IN_CHUNK]->(:Chunk)
(:RelationEvidence)-[:LEFT]->(:Concept)
(:RelationEvidence)-[:RIGHT]->(:Concept)
(:Concept)-[:RELATED_TO]->(:Concept)
(:Concept)-[:CANDIDATE_CLASS]->(:OntologyClass)
(:RelationEvidence)-[:CANDIDATE_TYPE]->(:RelationType)
```

### 8.2 查询增强

Neo4j 只在 Soft Gate 有 warning 时触发。

```python
class Neo4jOntologyEnhancementService:
    async def enhance(
        self,
        *,
        query: str,
        direct_evidence: tuple[MaterializedEvidence, ...],
        warnings: tuple[RagAnswerabilityWarningReason, ...],
        resource_id: str,
        corpus_version: str,
        request_scope: KnowledgeSearchRequestScope,
    ) -> GraphEnhancementResult:
        cache_key = self._cache.build_graph_key(
            direct_evidence_signature=hash_evidence_ids(direct_evidence),
            warning_signature=hash_warnings(warnings),
            graph_version=corpus_version,
            ontology_schema_version=self._ontology_schema_version,
            request_scope=request_scope,
            # permission scope slot: 权限模型确定后纳入 key。
        )
        cached = await self._cache.get_graph_enhancement(cache_key)
        if cached:
            return cached

        seed_chunk_ids = tuple(item.child_chunk_id for item in direct_evidence)
        seed_concepts = await self._neo4j.find_concepts_by_chunks(
            resource_id=resource_id,
            corpus_version=corpus_version,
            chunk_ids=seed_chunk_ids,
        )

        graph_result = await self._neo4j.expand_for_warnings(
            query=query,
            seed_concepts=seed_concepts,
            warnings=warnings,
            resource_id=resource_id,
            corpus_version=corpus_version,
            # permission filter slot: 权限模型确定后追加。
        )
        await self._cache.put_graph_enhancement(cache_key, graph_result)
        return graph_result
```

输出保持独立：

```text
direct_evidence: Qdrant 主召回 + RankingEngine topK
graph_evidence: Neo4j 补充证据，需要再 materialize
ontology_hints: 概念/关系/路径提示，不当作证据文本
concept_paths: 多跳路径解释
```

## 9. Evidence materialization

Qdrant 和 Neo4j 返回的是 id 与 score，Context Builder 需要可引用 evidence view。

```python
@dataclass(frozen=True, slots=True)
class MaterializedEvidence:
    child_chunk_id: str
    parent_chunk_id: str
    evidence_text: str
    parent_context: str
    page_label: str | None
    section_path: tuple[str, ...]
    anchor_labels: tuple[str, ...]
    start_offset: int | None
    end_offset: int | None
    score: float | None = None
```

```python
class EvidenceMaterializer:
    async def materialize_ranked(
        self,
        ranked: tuple[RankedCandidate, ...],
        *,
        resource_id: str,
        corpus_version: str,
        request_scope: KnowledgeSearchRequestScope,
    ) -> tuple[MaterializedEvidence, ...]:
        chunk_ids = tuple(item.candidate_id for item in ranked)
        cache_key = self._cache.build_materialized_evidence_key(
            resource_id=resource_id,
            corpus_version=corpus_version,
            request_scope=request_scope,
            chunk_ids=chunk_ids,
            # permission scope slot: 权限模型确定后纳入 key。
        )

        cached = await self._cache.get_materialized_evidence(cache_key)
        if cached:
            return cached

        children = await self._corpus.load_child_chunks(chunk_ids)
        parent_ids = tuple(dict.fromkeys(child.parent_chunk_id for child in children))
        parents = await self._corpus.load_parent_chunks(parent_ids)
        materialized = build_materialized_evidence(
            ranked=ranked,
            children=children,
            parents=parents,
        )
        await self._cache.put_materialized_evidence(cache_key, materialized)
        return materialized
```

权限模型未确定前，这个缓存不能做跨用户或跨权限域复用。第一阶段可以先实现“无缓存批量回源”，等权限 scope key 明确后再接 Redis
短 TTL 缓存。

## 10. 缓存体系

缓存不改变主链路职责，只减少重复计算和重复回源。

### 10.1 Ingestion deterministic cache

优化对象：

- Markdown chunking。
- Context Indexing 小模型调用。
- dense embedding。
- sparse/BM25 编码。
- graph extraction。

Key 维度：

```text
document_id
document_version
content_hash
chunking_pipeline_name
chunking_pipeline_version
context_indexing_model_version
context_indexing_prompt_version
embedding_model_version
sparse_encoder_version
graph_extraction_config_version
ontology_schema_version
```

伪代码：

```python
class RagIngestionDeterministicCache:
    async def get_context_indexing(
        self,
        *,
        child_content_hash: str,
        parent_content_hash: str,
        document_title_hash: str,
        model_version: str,
        prompt_version: str,
    ) -> ContextIndexingResult | None:
        ...

    async def get_embedding(
        self,
        *,
        indexing_text_hash: str,
        embedding_model_version: str,
    ) -> list[float] | None:
        ...
```

这个缓存与权限无关；它只缓存内容派生产物。

### 10.2 Evidence materialization cache

优化对象：

- `child_chunk_id -> RagChildChunk` 回源。
- `parent_chunk_id -> RagParentChunk` 回源。
- citation / locator / parent context 组装。

Key 维度：

```text
resource_id
session_id
corpus_version
chunk_ids_signature
context_window_config
permission scope slot
short ttl
```

当前不实现权限相关 key，只保留文档中的插槽。权限模型确定前，生产查询默认走 batch source loading。

### 10.3 Graph enhancement cache

优化对象：

- seed concept 查找。
- concept path expansion。
- RelationEvidence 查询。
- OntologyClass / RelationType 对齐。
- ontology hints 生成。

Key 维度：

```text
direct_evidence_signature
warning_signature
graph_version
ontology_schema_version
enhancement_strategy_version
permission scope slot
short ttl
```

缓存 value 只保存：

```text
graph_evidence_ids
ontology_hints
concept_paths
trace summary
```

不保存 final answer，不保存跨权限可复用的完整 evidence text。

### 10.4 Retrieval idempotency cache

这是低优先级工程去重，只处理完全相同请求的短 TTL retry：

```text
normalized_query
resource_id
retrieval_profile
corpus_version
candidate_limit
top_k
permission scope slot
```

它不做 semantic query cache，也不跨用户复用。

## 11. 权限接入位置

当前文档只标位置，不定义权限模型。

后续权限模型确定后，新增独立模块负责：

- 从上游 ACL 生成权限投影。
- 为 Qdrant filter、Elastic filter、Neo4j Cypher 生成权限约束。
- 为 materialization cache / graph cache 生成 permission scope key。
- 在 prompt 前做必要 hard auth 兜底。

插入点：

```text
RagIngestionApplicationService
  -> 写入权限投影到独立模型或各后端检索投影

RagElasticRepository.strict_prefilter
  -> append permission filter

RagQdrantRepository.retrieve
  -> append permission filter

RagNeo4jRepository.expand_for_warnings
  -> append permission predicate

EvidenceMaterializer
  -> cache key includes permission scope
  -> prompt 前 hard auth
```

禁止把权限字段提前塞进 `RagChildChunk`、`RagParentChunk` 或 `RagChunkExtraIndex`。这些模型只表达内容、分块、证据定位。

## 12. 后续落地顺序

建议按下面顺序开发，避免一上来把权限和缓存搅进主链路：

1. Corpus Store repository：保存 parent / child chunk 与 `extra_indexes`。
2. Qdrant repository：child chunk dense + sparse 写入与主召回。
3. Elastic repository：strict prefilter 与 locator 查询。
4. Evidence materializer：先做无缓存批量回源。
5. `KnowledgeSearchApplicationService`：串起 Elastic -> Qdrant -> Ranking -> Gate -> materializer -> Context Builder。
6. Neo4j ingestion / enhancement：先写图入库和 Soft Gate 后置增强。
7. Ingestion deterministic cache：优先缓存 embedding / context indexing。
8. 权限模型确定后接 filter builder、permission scope key、prompt 前 hard auth。
9. 最后再开 materialization cache 和 graph enhancement cache。
