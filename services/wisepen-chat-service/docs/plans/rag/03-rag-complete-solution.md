# WisePen 私有知识库 RAG 完整方案

日期：2026-06-27  
状态：方案定稿草案，供后续实现评审使用。  
关联文档：

- [RAG 资源权限模型（第一版）](02-rag-resource-permission-model.md)

## 1. 总体结论

WisePen 私有知识库 RAG 第一版采用：

```text
长期知识库 Corpus
  -> parent-child chunking
  -> Context Indexing
  -> Qdrant dense retrieval + Elasticsearch lexical retrieval
  -> application-side RRF fusion
  -> WisePen Ranking/Rerank/Context Builder
  -> answer with citations

旁路增强：
seed chunks
  -> typeless concept graph
  -> limited graph exploration
  -> evidence chunks
  -> Context Builder
```

权限模型定稿：

```text
Java wisepen-resource-service = 权限事实源
VIEW = RAG 查询准入
chunk 继承 resource_id 权限
预计算 ACL projection = RAG 检索强制准入条件
Qdrant / Mongo 检索必须先带 ACL filter
ResourceClient.check_res_permission() = prompt 前防陈旧兜底硬鉴权
```

第一版必须坚持三条硬边界：

1. `cnt_*`、`tfile_*`、`web_content_cache` 都不是长期知识库 ID 或权限载体。
2. `chunking_engine` 和 `ranking_engine` 只做共享基础能力，不承担权限、持久化、抓取或模型输出。
3. RAG 召回阶段必须使用预计算 ACL 过滤；进入 prompt 的任何知识库上下文还必须通过 resource-service 的 `VIEW` 硬鉴权。

## 2. 非目标

第一版不做：

- 段落级、父块级、子块级独立 ACL。
- 独立 `QUERY` 权限动作。
- GraphRAG Global Search、community summary、LightRAG server、Graphiti temporal graph、Neo4j。
- 让 Agent 直接传任意 graph node id 做全图探索。
- 把 web/document 工具输出自动变成长期 KB。
- 把 Qdrant filter 当成最终安全边界。
- 先无权限召回 topK，再逐条调用 resource-service 过滤。RAG 主检索必须先用预计算 ACL 裁剪候选。

这些能力可以作为后续 POC 或二期规划，但不进入第一版主链。

## 3. 当前可复用基础

| 能力 | 当前入口 | 在 RAG 中的用法 |
| --- | --- | --- |
| Markdown / parent-child chunking | `src/chat/application/utils/chunking_engine/` | 使用 `NESTED_MARKDOWN_PIPELINE` 产出 parent/child chunks。 |
| 排序与融合 | `src/chat/application/utils/ranking_engine/` | 将 Qdrant / Elasticsearch 命中映射为 `RankCandidate` 后复用 RRF/rerank/MMR。 |
| 小模型和 embedding | `src/chat/application/utils/llm_clients/` | 用于 query embedding、chunk embedding、context summary、结构化抽取。 |
| Mongo/Beanie | `src/chat/domain/entities/` 与 `src/chat/core/persistence/mongo/` | 存储 KB 文档、版本、chunk、graph、权限投影。 |
| Qdrant 配置 | `AppSettings.QDRANT_*` | 新增 KB dense chunk collection，不复用 mem0 collection。 |
| Elasticsearch 配置 | `AppSettings.ELASTIC_SEARCH_*` | 已有部署，可新增 KB lexical chunk index，承担第一阶段关键词/BM25 召回。 |
| 资源权限 RPC | `ResourceClient.check_res_permission()` | 构建/刷新 ACL projection 的事实校验入口，以及 prompt 前防陈旧兜底硬鉴权。 |
| 工具返回切面 | `ToolReturn` / `ToolOutputCache` | RAG 工具若返回长 evidence，本轮可生成 `cnt_*`，但不能把它当长期 ID。 |

## 4. 架构分层

建议新增长期 RAG 子系统：

```text
src/chat/application/rag/
  ingestion/
  retrieval/
  permission/
  graph/
  context_builder/
  evaluation/
  models.py

src/chat/domain/entities/rag/
src/chat/domain/repositories/rag/

src/chat/core/persistence/mongo/rag/
src/chat/core/persistence/qdrant/
src/chat/core/persistence/elasticsearch/
```

如需暴露给模型，再新增薄工具门面：

```text
src/chat/application/tools/rag_tools/
  knowledge_search_tool.py
  knowledge_graph_explore_tool.py
```

职责边界：

| 层 | 职责 | 禁止 |
| --- | --- | --- |
| `application/rag` | 长期 KB 入库、检索、权限、图谱、上下文构建 | 不生成 XML，不直接暴露内部存储 ID 给模型。 |
| `tools/rag_tools` | 模型可见工具 schema、preflight、service 调度、错误包装 | 不实现检索算法，不直接查 Qdrant/Mongo。 |
| `core/persistence/qdrant` | Qdrant collection/upsert/search/payload update | 不表达业务权限结论，只执行传入 filter。 |
| `core/persistence/elasticsearch` | Elasticsearch index/bulk/search/update | 不表达业务权限结论，只执行传入 filter。 |
| `core/persistence/mongo/rag` | KB/graph Mongo repository | 不调用 LLM，不组装 prompt。 |
| `domain/entities/rag` | 长期业务实体 | 不依赖 tool runtime 协议。 |

## 5. 长期数据模型

### 5.1 Corpus 主线

```text
kb_spaces
  _id
  owner_id
  name
  status
  created_at
  updated_at

kb_documents
  _id
  kb_id
  resource_id
  owner_id
  title
  source_kind
  current_version_id
  status
  acl_version
  acl_projection
  projection_status
  created_at
  updated_at

kb_document_versions
  _id
  kb_id
  document_id
  resource_id
  version_no
  source_hash
  parser
  parser_version
  markdown_storage_ref
  markdown_length
  status
  acl_version
  acl_projection
  projection_status
  created_at

kb_parent_chunks
  _id
  kb_id
  document_id
  document_version_id
  resource_id
  parent_chunk_id
  chunk_index
  start_offset
  end_offset
  content_hash
  section_path
  page_range
  summary
  child_count
  acl_version
  acl_projection
  projection_status

kb_child_chunks
  _id
  kb_id
  document_id
  document_version_id
  resource_id
  parent_chunk_id
  child_chunk_id
  child_index
  child_count
  start_offset
  end_offset
  evidence_text
  indexing_text
  section_path
  page
  anchor_names
  content_hash
  qdrant_point_id
  acl_version
  acl_projection
  projection_status
```

说明：

- `resource_id` 是权限根，不是 `document_id`。
- `document_id` 和 `document_version_id` 是 RAG 内部长期对象。
- child chunk 需要保存 `evidence_text`，因为 child 可能有 overlap，不能总是从 parent offset 精确还原。
- parent chunk 可只保存 offset 和 summary，实际正文从版本 Markdown 切片还原。
- `projection_status=active` 是进入检索索引的前置条件；缺失或失败的权限投影不能被召回。

### 5.2 Qdrant collection

建议 collection：

```text
wisepen_kb_chunks_v1
```

向量：

```text
dense: 1024 dim cosine
```

payload 最小集合：

```text
kb_id
resource_id
owner_id
document_id
document_version_id
parent_chunk_id
child_chunk_id
qdrant_point_id
section_path
page
anchor_names
content_hash
deleted_at
acl_version
acl_projection
projection_status
```

Qdrant 只存 dense retrieval 和过滤必要信息。正文、权限事实、版本事实仍以 Mongo/resource-service 为准。Qdrant point 必须携带 active ACL projection；没有 active projection 的 point 应 tombstone、删除或不可检索。

### 5.3 Elasticsearch lexical index

既然 Elasticsearch 已经是既有基础设施，第一版建议把它纳入 RAG 主召回通道，承担 first-stage lexical retrieval，而不是只在 Qdrant dense 候选之后做本地 BM25 rerank。

建议 index：

```text
wisepen_kb_chunks_lexical_v1
```

字段建议：

```text
kb_id
resource_id
owner_id
document_id
document_version_id
parent_chunk_id
child_chunk_id
section_path
heading
anchor_names
important_terms
evidence_text
indexing_text
content_hash
deleted_at
acl_version
acl_projection
projection_status
```

检索职责：

- `multi_match` / `match` / `match_phrase` 用于正文、标题、章节、锚点、术语字段的 BM25 词法召回。
- `term` / `terms` / keyword subfield 用于 `resource_id`、`document_version_id`、锚点、错误码、版本号等精确过滤或强约束。
- `bool.filter` 承载 KB scope、状态、版本和 ACL projection，不参与相关性打分。
- `must_terms`、`quoted_phrases` 和 `minimum_should_match` 用于 `anchored_exact`，不能只依赖 BM25 排名。

Elasticsearch 也只是检索索引，不是权限事实源。它必须携带 active ACL projection，所有 lexical search 必须先带 ACL filter；进入 prompt 前仍由 resource-service 做 `VIEW` hard auth。

Qdrant sparse vector 可以作为后续补充或 Elastic 不可用时的 fallback，但第一版主 lexical channel 采用 Elasticsearch。

### 5.4 Concept Graph

```text
concept_nodes
  node_id
  kb_id
  display_name
  normalized_name
  summary
  representative_mentions
  kind_hint
  confidence
  status
  merged_into
  created_at
  updated_at

concept_mentions
  mention_id
  node_id
  kb_id
  resource_id
  document_id
  document_version_id
  child_chunk_id
  surface
  normalized_name
  local_text
  offsets
  acl_version

concept_aliases
  alias
  kb_id
  node_ids
  source
  confidence

edge_evidence
  evidence_id
  kb_id
  resource_id
  document_id
  document_version_id
  child_chunk_id
  left_node_id
  right_node_id
  relation_text
  evidence_text
  confidence
  acl_version

concept_edges
  edge_id
  kb_id
  left_node_id
  right_node_id
  canonical_relation
  evidence_count
  confidence
  updated_at

concept_edge_arcs
  arc_id
  kb_id
  from_node_id
  to_node_id
  edge_id
  evidence_ids
  acl_resource_ids
  updated_at
```

图谱规则：

- 图只做语义延伸，不做主检索。
- 图边必须能回源到 `edge_evidence -> child_chunk -> resource_id`。
- graph exploration 返回 path 和 evidence chunk，不返回裸边作为最终事实。
- 图 traversal 也要按 `resource_id` 和 ACL 过滤，最终进入 prompt 前仍要硬鉴权。

## 6. 权限模型

### 6.1 权限事实源与检索准入

Java `wisepen-resource-service` 是唯一权限事实源。Chat Service RAG 保存的 `acl_projection` 是由该事实源派生出的检索准入投影，不是可选优化。

权限判断：

```text
can_enter_rag_context(resource_id, user_id, group_role_map)
  = ResourceClient.check_res_permission(resource_id, user_id, group_role_map)
      .allowedActions contains "VIEW"
```

现有调用入口：

```python
await ResourceClient.check_res_permission(
    resource_id=resource_id,
    user_id=SecurityContextHolder.get_user_id(),
    group_role_map=SecurityContextHolder.get_group_role_map(),
)
```

RAG 主检索必须先使用 `acl_projection` 过滤候选。`ResourceClient.check_res_permission()` 只用于：

- 构建或刷新 `acl_projection` 时校验权限事实。
- prompt 注入前防止 ACL projection 陈旧。
- resource-service 发现权限已撤回时 fail closed。

禁止路径：

```text
Qdrant 无 ACL filter 召回 topK
  -> 再逐条调用 resource-service 过滤
```

这种做法会把未授权 chunk 暴露给 ranking/rerank/logging/intermediate result，不能作为 RAG 主链。

### 6.2 权限继承

```text
resource_id
  -> document_id / document_version_id
    -> parent_chunk_id
      -> child_chunk_id
```

第一版规则：

- resource 有真实权限。
- document/version/chunk 都继承 resource 权限。
- parent chunk ACL = resource ACL。
- child chunk ACL = resource ACL。
- chunk 不能比 resource 更宽，也暂不支持更窄。

### 6.3 ACL Projection

`acl_projection` 是 RAG 检索层的强制字段。没有有效 `acl_projection` 的文档、parent chunk、child chunk 和 Qdrant point 不允许进入 `indexed` 状态，也不允许被检索。

建议结构：

```text
acl_projection:
  acl_version
  owner_id
  spaces:
    group_id:
      base_mask
      user_masks:
        user_id: mask
  specified_users:
    user_id: mask
  projection_status: active | stale | failed
  projection_updated_at
  projection_source_event_id
```

第一版 RAG 只判断 `VIEW`。只要 `VIEW` 不在最终 mask 中，该资源及其所有 chunks 都不能参与 RAG。

投影必须写入：

```text
kb_documents
kb_document_versions
kb_parent_chunks
kb_child_chunks
Qdrant child point payload
concept_mentions / edge_evidence 的 acl_version 或 acl_resource_ids
```

Qdrant payload 中可以只保留过滤所需的最小投影，但必须足够在向量检索阶段判断当前用户是否有 `VIEW`。

### 6.4 Qdrant / Mongo ACL Filter

检索前从安全上下文拿：

```text
user_id
group_role_map
allowed kb/resource scope
```

构造 Qdrant filter，逻辑等价：

```text
deleted_at is null
AND projection_status == active
AND (
  owner_id == current_user
  OR acl_projection.specified_users[current_user] contains VIEW
  OR current_user is group OWNER / ADMIN for group in acl_projection.spaces
  OR acl_projection.spaces[group_id].user_masks[current_user] contains VIEW
  OR acl_projection.spaces[group_id].base_mask contains VIEW
)
```

Mongo 侧任何候选 hydrate、graph traversal 或 fallback retrieval 也必须带同等 ACL 条件。不能只在 Qdrant 侧过滤，然后让 Mongo/graph 旁路绕过权限。

ACL filter 的职责是保证未授权 chunk 不进入候选集、排序器、reranker、Context Builder 输入队列和中间日志。它仍不是最终安全边界，因为投影可能陈旧。

### 6.5 Prompt 前硬鉴权

Context Builder 在把任何 parent/chunk 放入 prompt 前，必须按 `resource_id` 去重并批量硬鉴权。

```text
candidate chunks
  -> group by resource_id
  -> ResourceClient.check_res_permission()
  -> drop resources without VIEW
  -> build prompt context
```

如果 resource-service 调用失败：

- 默认 fail closed：该 resource 的 context 不进入 prompt。
- 返回 warning 给工具 visible result 或审计日志。
- 不允许因为 ACL projection 已过滤就跳过硬鉴权。

### 6.6 权限变更同步

触发：

```text
资源绑定标签变化
标签权限变化
小组默认成员掩码变化
资源级覆盖变化
指定用户特权变化
用户小组角色变化
资源删除或恢复
```

流程：

```text
resource ACL event
  -> build permission projection from resource-service output
  -> update kb_documents / versions / parent_chunks / child_chunks first
  -> update Qdrant child point payload acl_projection
  -> mark projection_status=active only after Mongo + Qdrant are consistent enough for retrieval
  -> future retrieval must use new projection
  -> in-flight result still guarded by prompt hard auth
```

需要记录：

```text
acl_version
acl_projection_updated_at
projection_source_event_id
projection_status
```

失败策略：

- 新文档入库时 ACL projection 构建失败：文档版本不得进入 `indexed`。
- 已有文档 ACL 刷新失败：将 projection 标记为 `stale` 或 `failed`，默认不参与 RAG 检索，除非后续明确实现“陈旧但硬鉴权兜底”的降级开关。
- Qdrant payload 更新失败：对应 child points 不允许继续作为 active 候选；可以 tombstone、打 `projection_status=failed`，或暂停该 resource 的检索。

## 7. 入库流程

### 7.1 Source 到 document version

```text
resource_id
  -> load source file / url / asset metadata
  -> parse to normalized Markdown
  -> compute source_hash
  -> build acl_projection from resource-service
  -> create kb_document if needed
  -> create kb_document_version
```

原则：

- RAG 入库 service 可以复用现有解析能力的设计，但不直接把 `document_parse` 的 `cnt_*` 当长期内容。
- 若来源是资源服务/文件服务，RAG 应保存 `resource_id`、source hash、parser version。
- 同一个 `resource_id` 新版本入库后，旧版本 points 需要 tombstone 或按 version 删除。
- 入库阶段必须先拿到 active ACL projection；拿不到时文档版本停在 `permission_pending` 或 `failed_retryable`，不得写入可检索 Qdrant point。

### 7.2 Chunking

```text
Markdown
  -> ChunkingEngine + NESTED_MARKDOWN_PIPELINE
  -> parent chunks
  -> child chunks
  -> section/page/anchor indexes
```

字段映射：

| Chunking 字段 | RAG 落点 |
| --- | --- |
| `chunk.chunk_id` | `parent_chunk_id` / `child_chunk_id` |
| `chunk.level` | parent/child discriminator |
| `chunk.parent_chunk_id` | child -> parent 外键 |
| `chunk.start_offset/end_offset` | 版本 Markdown 定位 |
| `chunk.content_hash` | 幂等去重 |
| `metadata.section_paths` | section path |
| `metadata.anchor_names` | anchors |
| `metadata.child_index/child_count` | auto merge / parent expansion |

### 7.3 Context Indexing

对每个 child chunk 生成：

```text
indexing_text =
  document_title
  section_path
  context_summary
  important_terms
  child_text
```

保存：

- `evidence_text`：原始可引用 child 文本。
- `indexing_text`：用于 dense embedding、Elasticsearch BM25、图抽取消歧。

第一版 Context Indexing 必须调用小模型，不做 deterministic fallback。输入必须包含 `parent_text` 和 `child_text`；`parent_text` 是 child 所在父块全文，用于判断 child 的局部语义位置和术语边界。小模型失败时，入库任务应标记为可重试，不能写入低质量替代结果污染长期知识库。

### 7.4 Embedding 与检索索引写入

```text
child.indexing_text
  -> LiteLLMEmbeddingClient
  -> Qdrant upsert

child.indexing_text + fields
  -> Elasticsearch bulk index
```

写入顺序建议：

1. Mongo 写 document/version/parent/child records，状态 `indexing`。
2. 写入或刷新 active ACL projection。
3. 批量生成 embedding。
4. Qdrant upsert child points，payload 必须包含 active ACL projection。
5. Elasticsearch bulk index child docs，filter 字段必须包含 active ACL projection。
6. Mongo 标记 version/chunks `indexed`。
7. 失败时保留 ingestion run，支持 retry；任一检索索引写入失败时，该 version 不进入完整可检索状态。

### 7.5 Graph extraction

Graph extraction 可以异步落后于主索引：

```text
child indexing pack
  -> StructuredExtractionClient
  -> mention/relation/alias DTO
  -> Resolver
  -> AliasManager
  -> EdgeBuilder
  -> graph collections
```

抽取输入必须区分：

```text
semantic_context: 用于理解和消歧
evidence_source: 才能作为证据
```

低置信度 mention 不强行合并；宁愿新建 node 或标记待复核。

## 8. 查询流程

### 8.1 主线检索

```text
knowledge_search(request, kb_scope)
  -> security context
  -> validate main-model selected retrieval_profile and anchors
  -> RetrievalPlanBuilder maps profile to server-side weights
  -> build ACL filter from acl_projection and group_role_map
  -> query embedding + lexical query
  -> Qdrant dense search with mandatory ACL filter
  -> Elasticsearch lexical search with mandatory ACL filter
  -> application-side RRF fusion
  -> hydrate child/parent from Mongo
  -> drop stale/deleted/version-mismatch chunks
  -> RankingEngine rerank/diversify
  -> prompt hard auth by resource_id
  -> Context Builder
  -> visible citations + optional cacheable_texts
```

推荐初始参数：

```text
Qdrant dense top_k = 80
Elasticsearch lexical top_k = 80
application fusion = RRF
candidate_limit = 100-200
reranker top_n = 20-40
final context windows = 8-20
```

`request` 由主模型显式给出检索意图，但不允许直接控制底层任意权重：

```text
retrieval_profile = balanced | semantic | lexical | anchored_exact
query
semantic_query
lexical_terms
must_terms
quoted_phrases
entities
expected_answer_type
```

`RetrievalPlanBuilder` 根据 profile 选择服务端固定模板：

| profile | 适用场景 | 检索倾向 |
| --- | --- | --- |
| `balanced` | 默认问答、没有明显锚点 | Qdrant dense + Elasticsearch lexical 均衡，rerank 正常开启。 |
| `semantic` | 概念解释、同义表达、用户描述不精确 | dense 权重更高，允许 `semantic_query`，保留 lexical 兜底。 |
| `lexical` | 用户给出明确术语、标题、配置项、错误片段 | Elasticsearch BM25 / field boost 权重更高，dense 只补语义邻近。 |
| `anchored_exact` | 版本号、错误码、函数名、文件名、quoted phrase | `must_terms` / `quoted_phrases` / `KeywordScorer` 强约束，BM25 只是辅助词法相关性。 |

这里吸收 web search 重构经验：不引入小模型隐式路由，不让内部自动多跳改写 query 作为主控。拥有完整上下文的主模型负责显式选择 profile；RAG service 负责确定性执行、权限过滤和可审计检索。

BM25 只能承担 lexical relevance，不能单独承担“精确检索”。`anchored_exact` 必须由 `must_terms`、`quoted_phrases`、字段命中、`KeywordScorer(require_all_keywords=True)` 和必要 hard filter 共同实现。

主检索顺序是强约束：ACL filter 必须在 Qdrant 和 Elasticsearch 查询请求中生效，不能在两个索引返回后才做权限过滤。Qdrant dense、Elasticsearch lexical、fusion、topK 都必须发生在已授权候选集合内。

Mongo hydrate 也要复查：

```text
document/chunk status == indexed
projection_status == active
acl_version matches or is accepted by retrieval policy
document_version_id is current or explicitly requested
```

任何不满足条件的候选必须在进入 RankingEngine 前丢弃。

### 8.2 Parent expansion

```text
child hits
  -> group by parent_chunk_id
  -> if multiple children under same parent hit, prefer parent context
  -> otherwise use child window + surrounding parent slice
```

因为第一版 chunk 继承 resource 权限，child 命中后合并 parent 是权限安全的；但 parent 注入前仍要对 `resource_id` 硬鉴权。

### 8.3 Graph exploration

触发条件：

- 主线召回低置信度。
- 用户问题明显需要关系链、多跳、概念解释。
- seed chunks 命中明确 concept。
- Agent 或 service 判断需要补桥梁证据。

流程：

```text
seed child chunks
  -> concept_mentions
  -> seed node ids
  -> concept_edge_arcs $graphLookup maxDepth=1/2 with ACL/resource filter
  -> collect edge_evidence child_chunk_ids
  -> ACL projection filter before hydrate/rerank
  -> hydrate chunks
  -> prompt hard auth
  -> merge into Context Builder
```

`knowledge_graph_explore` 默认隐藏，只在已有可信 seed 时暴露或由内部 service 调用。

图探索不能先遍历全图再做权限过滤。Traversal 必须受限于用户可访问的 `resource_id` / `acl_projection`，否则关系路径本身就可能泄漏未授权知识的存在。

## 9. Context Builder

Context Builder 是唯一决定“什么进入 prompt”的 RAG 组件。

输入：

```text
direct retrieval candidates
graph expansion candidates
query metadata
token budget
security context
```

步骤：

1. 合并相同 `child_chunk_id`。
2. 按 `resource_id`、`document_id`、`parent_chunk_id` 去重。
3. 拒绝任何缺失 active ACL projection 的候选。
4. 对所有候选 resource 做硬鉴权。
5. 删除未通过 `VIEW` 的候选。
6. 按 ranking score、source diversity、parent merge 策略组装。
7. 生成 citation map。
8. 输出 prompt context 和模型可见摘要。

输出结构建议：

```text
RagContextBuildResult
  items:
    citation_id
    resource_id
    document_id
    document_version_id
    parent_chunk_id
    child_chunk_ids
    title
    section_path
    page
    excerpt
    source: direct | graph
    graph_path?
  warnings
  dropped_by_permission_count
  dropped_by_version_count
```

## 10. 模型可见工具

### 10.1 `knowledge_search`

用途：在用户授权的知识库范围内查找可引用证据。

默认策略：

- 可默认暴露，但必须依赖安全上下文。
- required context 至少包含 `user_id`、`session_id`，权限实际读取 `SecurityContextHolder` 或可信 context。
- 不允许模型传 `user_id`、group roles、ACL。

返回：

- 小结果直接普通结构化返回。
- 如果 evidence 很长，使用 `ToolReturn.cacheable_texts` 生成本轮 `cnt_*`。
- visible result 只暴露 citation、标题、章节、页码、短 excerpt、warnings、suggested action。

重要边界：

- `cnt_*` 只是本轮读取凭证，不是 KB ID。
- 不暴露 Qdrant point id、Mongo `_id`、acl_projection。

### 10.2 `knowledge_graph_explore`

用途：从可信 seed concepts/chunks 做有限跳数图延伸。

默认策略：

- `expose_by_default=False`。
- 只在上一轮 `knowledge_search` 返回 seed 后，由 coordinator 或 service 显式暴露。
- 不允许模型凭空传 node id；seed 应绑定服务端签发的短期引用或上一轮 visible seed。

返回：

```text
paths
  seed_concept
  relation_path
  target_concept
  evidence_citations
  reason
warnings
```

图探索结果进入 prompt 前，仍通过 Context Builder 和 resource-service 硬鉴权。

## 11. 后台任务与一致性

建议任务：

| 任务 | 触发 | 职责 |
| --- | --- | --- |
| `kb_ingestion_job` | 用户上传/绑定资源/资源更新 | 解析、chunk、index、写 Qdrant。 |
| `kb_acl_projection_refresh_job` | resource ACL event | 预计算并更新 Mongo/Qdrant ACL projection；失败时撤出可检索集合。 |
| `kb_graph_extraction_job` | chunk indexed | 抽取 mention/relation/alias。 |
| `kb_reindex_job` | embedding/parser/chunking version 变更 | 重建 collection 或文档版本索引。 |
| `kb_gc_job` | 文档删除/版本过期 | 删除或 tombstone Mongo/Qdrant/graph 记录。 |

一致性策略：

- Mongo 是 KB 元数据事实源。
- Qdrant 是检索索引，可重建。
- resource-service 是权限事实源。
- Graph 是可重算派生索引。
- 查询时发现 Qdrant hit 对应 Mongo 记录缺失或版本失效，直接丢弃并记录 warning。
- ACL projection 是检索准入投影；Mongo/Qdrant 中 projection 非 active 的对象默认不可检索。

## 12. 状态机

### 12.1 Document version

```text
created
  -> parsing
  -> parsed
  -> permission_pending
  -> permission_projected
  -> chunking
  -> indexing
  -> indexed
  -> graph_pending
  -> graph_indexed
  -> failed
  -> deleted
```

主检索只依赖 `indexed` 且 `projection_status=active`；图增强依赖 `graph_indexed`，但图未完成不阻断主检索。`permission_pending` / `projection_status != active` 的版本不得进入 Qdrant 可检索集合。

### 12.2 Ingestion run

```text
pending
  -> running
  -> succeeded
  -> failed_retryable
  -> failed_permanent
  -> canceled
```

每次 run 记录：

```text
resource_id
document_version_id
parser_version
chunking_version
embedding_model
graph_extraction_model
cost
duration
error_code
```

## 13. 目录和容器接线

需要进 container 的对象：

- Qdrant client 或 `KnowledgeVectorRepository`，因为它管理外部连接/共享 client。
- RAG tool 实例，因为需要注册到 `ToolRegistry`。
- 需要共享资源或后台生命周期的 ingestion/queue publisher。
- `ContextIndexingService` 使用轻量 LLM client，本身可按后续生命周期需要决定是否进容器。

不需要进 container 的对象：

- 轻量 DTO converter。
- prompt payload builder。
- 单调用临时 candidate/result。

settings 归属：

| 配置 | 归属 |
| --- | --- |
| Qdrant host/port/password | `app_settings`，已有。 |
| embedding model/dimensions | `app_settings`，已有。 |
| KB collection name | `app_settings` 或 RAG 专属 settings，偏基础设施。 |
| retrieval top_k/candidate_limit | RAG/tool settings，行为参数。 |
| graph max depth/fanout | RAG/tool settings，行为参数。 |
| ingestion batch size/concurrency | RAG/tool settings，行为参数。 |

## 14. 评估与验收

### 14.1 离线评估集

至少准备 50-100 个 query：

- 单文档事实问答。
- 多文档归纳。
- 多跳关系。
- 概念消歧。
- PDF 页码引用。
- 表格问答。
- 权限过滤。
- 文档版本更新。
- 删除/恢复资源。

### 14.2 指标

| 指标 | 目标 |
| --- | --- |
| recall@20 | gold evidence 应被召回。 |
| context precision@k | 前 k 个上下文少噪声。 |
| citation correctness | 引用 resource/document/page/chunk 正确。 |
| permission leakage | 必须为 0。 |
| answer faithfulness | 答案不得使用未提供证据。 |
| p95 latency | 分主检索、rerank、硬鉴权、context build 统计。 |

### 14.3 权限专项用例

必须覆盖：

- owner 可检索。
- GROUP OWNER / ADMIN 可检索。
- 普通成员通过 base mask 获得 `VIEW` 可检索。
- specified user 获得 `VIEW` 可检索。
- blacklist / no VIEW 不可检索。
- 只有 `DISCOVER` 不可进入 RAG。
- 无 active ACL projection 不可进入 Qdrant 候选。
- Qdrant 检索请求必须携带 ACL filter；无 filter 的知识库检索应被 preflight 或 service 层拒绝。
- Qdrant 投影过期但 resource-service 已撤权：prompt 前硬鉴权必须拦截。
- resource-service 调用失败：fail closed。

## 15. 分阶段实施

### Phase 0：方案与评估基线

产物：

- 本完整方案文档。
- eval queries 初稿。
- RAG 数据模型草案。
- Qdrant collection schema 草案。

验收：

- 权限模型评审通过。
- 明确第一版不做 chunk 级特殊 ACL。

### Phase 1：Corpus + 权限投影

产物：

- `kb_documents` / `kb_document_versions`。
- `AclProjection` DTO。
- `RagPermissionChecker`。
- `QdrantAclFilterBuilder`。
- ACL 投影刷新流程。

验收：

- 给定 resource_id，可以保存并更新 `acl_projection`。
- `VIEW` 硬鉴权封装与 `ResourceClient.check_res_permission()` 的语义一致。
- 没有 active ACL projection 的文档版本、parent chunk、child chunk 和 Qdrant point 不能进入检索。
- Qdrant filter builder 能根据 `user_id + group_role_map` 生成 VIEW 过滤条件。

### Phase 2：Chunking + Qdrant 主检索

产物：

- parent/child chunk persistence。
- LLM-required Context Indexing。
- Qdrant upsert/search repository。
- Elasticsearch lexical index/search repository。
- `RagRetrievalRequest`：主模型显式传入 `retrieval_profile`、anchors 和 query metadata。
- `RetrievalPlanBuilder`：将 profile 映射为服务端固定权重模板，拒绝模型传任意底层权重。
- `knowledge_search` service。

验收：

- 能在授权资源中召回 evidence。
- `balanced` / `semantic` / `lexical` / `anchored_exact` profile 能生成稳定、可测试的 Qdrant + Elasticsearch 检索计划。
- `anchored_exact` 不把 BM25 当作唯一精确条件，必须验证 Elastic `must_terms` / `quoted_phrases` / keyword hard constraints。
- 未授权资源不会进入 Qdrant 候选、RankingEngine 候选和 prompt。
- 文档更新后旧版本不再召回。

### Phase 3：Rerank + Context Builder + Tool

产物：

- RAG ranking pipeline。
- parent expansion。
- citation map。
- `knowledge_search_tool.py`。

验收：

- 工具返回结构化 citations。
- 长 evidence 正确走 `ToolReturn.cacheable_texts`。
- 不暴露内部 storage id、Qdrant point id、acl_projection。

### Phase 4：Graph extraction

产物：

- Structured extraction client。
- concept graph Mongo 集合。
- Resolver / AliasManager / EdgeBuilder。
- graph extraction job。

验收：

- edge evidence 全部可回源 chunk。
- 图谱失败不影响主检索。

### Phase 5：Graph explore

产物：

- graph exploration service。
- `knowledge_graph_explore_tool.py` 或内部 route。
- graph path + evidence context merge。

验收：

- 无 seed 不探索。
- maxDepth/fanout 生效。
- graph evidence 进入 prompt 前硬鉴权。

### Phase 6：重建、删除、审计

产物：

- reindex job。
- Qdrant blue-green collection 迁移策略。
- resource delete / restore 同步。
- 审计日志和权限泄漏测试。

验收：

- 删除资源后 Mongo/Qdrant/graph 都不可召回。
- embedding 模型切换可重建。

## 16. 风险与控制

| 风险 | 控制 |
| --- | --- |
| 权限投影过期 | ACL event 刷新投影；projection 非 active 默认不可检索；prompt 前硬鉴权只做防陈旧兜底。 |
| Qdrant filter 写错 | `QdrantAclFilterBuilder` 单测、集成权限用例、无 filter 请求拒绝；resource-service 硬鉴权仅兜底。 |
| Graph 裸边被误用 | graph 只返回 evidence chunk，Context Builder 只注入 chunk 文本。 |
| chunk 合并越权 | 第一版 chunk 继承 resource ACL；parent 注入前仍硬鉴权。 |
| 文档版本污染 | 所有 chunk/point/edge 带 `document_version_id`。 |
| 第三方依赖反向约束 | qdrant/instructor/ragas 只在 adapter/eval 层出现。 |
| Rerank 成本高 | candidate_limit/top_n 可配置，保留无 reranker 降级路径。 |
| resource-service 不可用 | fail closed，返回 warning，不注入相关资源。 |

## 17. 最终定稿规则

```text
RAG 是长期业务索引体系，不是工具缓存体系。
resource_id 是权限根。
VIEW 是第一版 RAG 查询权限。
预计算 ACL projection 是 RAG 检索强制准入条件。
没有 active ACL projection 的对象不可检索。
Qdrant/Mongo/Graph 检索必须先做 ACL filter。
Qdrant 是检索索引，不是事实源。
Mongo 是 KB/graph 元数据事实源。
resource-service 是权限事实源。
Context Builder 是 prompt 注入唯一入口。
所有进入 prompt 的 KB context 必须通过 VIEW 硬鉴权，但硬鉴权不能替代检索前 ACL filter。
```
