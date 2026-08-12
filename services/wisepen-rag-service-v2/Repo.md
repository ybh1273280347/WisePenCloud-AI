# WisePen RAG Service v2 仓储与数据设计

本文档在 [Architecture.md](./Architecture.md) 的六个能力边界下，确定 v2 的仓储职责和数据布局。结论来自 v1 repository 协议、Mongo collection、Qdrant payload、Neo4j schema、Redis state 以及真实调用链的反向排查。

这里保留的是必要能力和数据不变量，不保留 v1 的仓储名称、类边界或 projection/snapshot 语义。

## 1. 设计结论

### 1.1 仓储不是数据表

仓储 port 按 application 能力的使用方式划分，物理数据按一致性、查询方式和生命周期划分。两者不要求一一对应：

- 同一组 Mongo 内容表可以分别实现 `index`、`read`、`verify` 的 port。
- 同一个 Qdrant collection 同时支撑写入和召回，但读写 port 必须分离。
- 同一个 Neo4j schema 同时支撑写图、mention 查询、路径扩展和 ACL 同步，但四种职责不能合并成一个 application repository。
- Redis navigation state 是 locate/read/expand 的协作数据，不因此新增第七个 application 能力。

### 1.2 最终原则

- application 依赖语义 port，不能依赖 Mongo Document、Qdrant Point、Neo4j Record 或 Redis key。
- 仓储 port 放在 `domain/repositories`，使用 `Protocol` 表达跨层依赖；Beanie Mongo 文档实体放在 `domain/entities`。
- persistence adapter 实现 port，domain 和 application 不反向导入 persistence model。
- 仓储方法按业务动作命名，不使用 `projection`、`snapshot`、`materialize`、`derived` 等无法说明读写内容的词。
- 批量参数使用 `Sequence`/`list`，按 key 返回的数据使用 `dict`；不把 tuple 当默认仓储契约。
- 未找到是正常批量读取语义时只省略对应 key；一致性损坏、revision 冲突和依赖失败直接抛出异常。
- v2 使用独立 Mongo collection、Qdrant collection、Neo4j namespace 和 Redis prefix，不能原地复用 v1 数据结构。

## 2. v2 逻辑仓储 port

以下名称描述稳定职责。实现可以继续拆文件，但不能改变 owner 或把相邻阶段重新混合。

### 2.1 index

#### `ResourceIndexWriter`

负责 Mongo 中一个资源索引 revision 的完整生命周期：

- 判断文档事件是需要 stage、已经 applied，还是 stale。
- 写入 revision 元数据、原始 Markdown parts、Section、ReadingBlock 和 SourceRef。
- 最后写入 staged revision 指针，使未完整写完的数据永远不可见。
- 通过 resource-level CAS 发布 applied revision。
- 删除资源的全部内容 revision 和索引状态。

它不对外提供状态、revision、原文或图构建输入读取。写入过程内部可以查询状态以完成 CAS、幂等和并发判断。

它合并 v1 的 `RagContentProjectionRepository`、`RagContentCheckpointRepository` 和 `RagKnowledgeExtractionSourceRepository` 的写入侧职责。图构建输入属于同一个 `index` 能力，不再为它单独建立 source repository。

#### `RetrievalIndexWriter`

负责 Qdrant retrieval chunk 的写入生命周期：

- 初始化 collection、vector 和必要 payload index。
- 查找可复用 dense vector。
- 写入未发布 revision 的 retrieval points。
- 激活当前 revision 并停用/删除同资源旧 revision。
- 删除资源全部 points。

它不执行 locate 查询，也不负责 ACL 规则计算。

#### `KnowledgeGraphWriter`

负责 Neo4j 图写入生命周期：

- 初始化 constraint/index。
- 开始某个 content revision 的图构建并使旧图不可见。
- 写入规范化节点、MENTIONS 和知识关系。
- 发布或明确跳过当前 graph revision。
- 清理旧关系、旧 mention 和孤立节点。
- 删除资源图数据。

它替代 `KnowledgeGraphProjectionRepository`。写入的是知识图谱，不再创造 `KnowledgeGraphProjection` 业务实体。

#### `ModelGenerationCache`

缓存 index 内两类昂贵且确定性的模型结果：

- RetrievalChunk contextual text。
- GraphRAG 候选抽取结果。

使用 `resource_id + cache_kind + cache_key` 读写字符串 payload。`cache_kind` 是必要的存储判别枚举，不是对外业务字段。cache key 必须包含 prompt/schema/model/profile 和完整输入指纹。

### 2.2 locate

#### `CandidateSearch`

负责从 Qdrant 返回混合召回命中：

- dense 与 BM25 查询及 Qdrant 内部融合。
- resource、active revision 和 ACL 条件下推。
- 只映射 locate/rerank 确实需要的 payload 字段。

它不负责 query embedding、application rerank、ReadingBlock 去重或最终 ACL 复查。这些属于 `locate` 用例本身。

#### `MentionLookup`

根据已核验 SourceRef 查询当前已发布图中的 MENTIONS 节点。它是 locate 进入图探索的入口，不提供任意路径遍历。

#### `NavigationStateStore`

`locate` 拥有该 port 的定义与 state 创建语义：

- 创建绑定 user/session/root query 的 state。
- 读取 state。
- 原子追加 known sections。
- 原子追加 known nodes。

`read` 与 `expand` 只能使用其公开访问契约，不能依赖 Redis 实现。

### 2.3 read

#### `AppliedStructureReader`

只读取 applied revision 的 document structure、页目录和 Section 树，不读取正文。

#### `AppliedContentReader`

- 按 page label 读取原文窗口。
- 按 Section ID 读取正文块。
- 读取 Section frontier。

#### `GraphBuildSourceReader`

只为 index 内图构建阶段读取指定 applied revision 的 Markdown、Section、ReadingBlock 和 SourceRef。它不是通用内容读取仓储，也不属于写入 port。

structure、page、section 是不同方法和返回契约，但共用同一个内容事实源。仓储只返回存在的数据，不生成 `page_not_found`、`section_not_found` 或 `section_empty`。

### 2.4 expand

#### `GraphTraversal`

负责 Neo4j 当前已发布图上的有界路径查询：

- seed node、relation type、方向、深度和 limit 过滤。
- ResourceNode 与 evidence resource 的 ACL 条件。
- content revision 与 graph revision 有效性过滤。
- 返回 node、edge、path 和 evidence SourceRef 身份。

它不排序路径、不修改 navigation state、不读取正文证据。排序和 state 扩展属于 `expand` 用例，证据读取属于 `verify`。

### 2.5 verify

#### `EvidenceReader`

负责从 applied revision 读取并核验权威证据：

- 按资源和 SourceRef ID 读取 source spans 对应的 Markdown。
- 按资源和 ReadingBlock ID 读取正文块。
- 确认 SourceRef、RetrievalChunk、ReadingBlock、Section 和 revision 的归属一致。
- 缺失 part、span 越界、content hash 不一致时直接抛出数据一致性异常。

它替代 `RagSourceRepository`。最终 ACL 复查由 `verify` 用例调用 `acl` 完成，不塞进 Mongo adapter。

### 2.6 acl

#### `AuthoritativeAclReader`

只读 Java Resource Mongo 的权威资源 ACL，并映射为 RAG 使用的稳定权限事实。它不读写 v2 本地 ACL collection。

#### `ResourceAclStore`

读写 RAG 本地 ACL：

- 按 resource ID 读取单个或批量 ACL。
- 按 acl revision 幂等 upsert。
- 删除资源 ACL。

#### `RetrievalAclWriter`

只负责把已计算 ACL 同步到 Qdrant points。

#### `GraphAclWriter`

只负责把已计算 ACL 同步到 Neo4j ResourceNode/ResourceGroupAcl。

删除 v1 的通用 `RagAclProjectionTarget`。ACL 同步用例显式依赖 retrieval 与 graph 两个 target，不能用任意 target 列表隐藏实际副作用。

## 3. v1 仓储职责处理结果

| v1 职责 | v2 处理 | 理由 |
| --- | --- | --- |
| `RagContentProjectionRepository` | 与 checkpoint、图构建 source 合并为 `ResourceIndexWriter` | 三者共同维护同一 content revision 的写入与发布，不是独立业务能力。 |
| `RagContentCheckpointRepository` | 删除独立 port | applied/staged 指针是资源索引状态的一部分；locate 不应直接依赖写入 checkpoint。 |
| `RagKnowledgeExtractionSourceRepository` | 改为 `GraphBuildSourceReader` | 只被 index 的图构建阶段消费，不属于索引写入 port 或通用正文读取。 |
| `RagResourceSnapshotRepository` | 删除并拆为 `AppliedStructureReader` 与 `AppliedContentReader` | `snapshot` 同时混入结构与正文读取，名称和职责都错误。 |
| `RagSectionNavigationRepository` | 合并到 `AppliedContentReader` 的正文读取侧 | Section frontier 与 Section 正文都属于已发布内容读取，但不再和结构获取混在同一 port。 |
| `RagSourceRepository` | 修改为 `EvidenceReader` | 精确保留 SourceRef/ReadingBlock 回源能力，去除宽泛 source 命名。 |
| `RagVectorIndexRepository` | 修改为 `RetrievalIndexWriter` | 保留 Qdrant 写侧边界，名称明确它不做 locate。 |
| `RagCandidateRepository` | 修改为 `CandidateSearch` | 这是外部检索 port，不是持久化聚合根 repository。 |
| `KnowledgeGraphProjectionRepository` | 修改为 `KnowledgeGraphWriter` | 实际职责是构建、发布、跳过和删除图，不是字段投影。 |
| `KnowledgeGraphNavigationRepository` | 拆为 `MentionLookup` 与 `GraphTraversal` | locate 的 mention 解析和 expand 的路径遍历是两个不同问题。 |
| `KnowledgeNavigationStateRepository` | 保留职责并改为 `NavigationStateStore` | state 有独立 TTL、原子集合扩展和跨请求生命周期，确实需要仓储。 |
| `RagAclProjectionRepository` | 拆为 `AuthoritativeAclReader` 与 `ResourceAclStore` | v1 一个类同时访问上游库和本地库，混淆权威来源与本地读取。 |
| `RagAclProjectionTarget` | 删除 | 通用 target 隐藏 Qdrant/Neo4j 两个明确副作用和失败位置。 |
| `RagContextIndexingRepository` | 与 graph extraction cache 合并为 `ModelGenerationCache` | 两者都是 resource-scoped、content-addressed 的模型生成缓存，生命周期一致。 |
| `KnowledgeGraphDerivedRepository` | 与 contextual cache 合并 | `derived` 过于抽象，且实际只保存 GraphRAG 模型输出缓存。 |
| `RagResourceDeletionTarget` | 删除 | 通过 duck typing 遍历 target 会隐藏删除顺序和遗漏；index 删除用例应显式调用每个 store。 |

## 4. Mongo 数据设计

v1 当前有 10 个 RAG collection。v2 收敛为 8 个，并全部使用独立的 `wisepen_rag_v2_*` 名称。

### 4.1 collection 决策总表

| v1 collection | 处理 | v2 collection | 明确理由 |
| --- | --- | --- | --- |
| `wisepen_rag_projection_checkpoints` | 修改、重命名 | `wisepen_rag_v2_resource_index_states` | 这是每资源 staged/applied 发布指针，不是 projection checkpoint。 |
| `wisepen_rag_content_revisions` | 保留、修改 | `wisepen_rag_v2_content_revisions` | revision 元数据有独立多版本生命周期，是所有读取的内容身份。 |
| `wisepen_rag_content_parts` | 保留、重命名 | `wisepen_rag_v2_source_parts` | 原始 Markdown 可能超过 BSON 上限，必须分片；其语义是权威 source，不是任意 content part。 |
| `wisepen_rag_pages` | 删除、合并 | 嵌入 `content_revisions.pages` | page range 轻量、总是随 revision 读写、没有独立生命周期；单独 collection 是多余实体。 |
| `wisepen_rag_sections` | 保留、修改 | `wisepen_rag_v2_sections` | 标题树需要按 ID、parent、ordinal 和原文范围独立查询。 |
| `wisepen_rag_section_reading_blocks` | 保留、修改 | `wisepen_rag_v2_reading_blocks` | 正文块可能很多且体积大，需要按 block/section/range 查询，不能嵌入 Section。 |
| `wisepen_rag_source_refs` | 保留、修改 | `wisepen_rag_v2_source_refs` | verify 与 graph evidence 都依赖稳定 SourceRef，不能只存在于 Qdrant。 |
| `wisepen_rag_context_indexing` | 合并 | `wisepen_rag_v2_generation_cache` | 与图抽取缓存具有相同 key/value 和删除生命周期。 |
| `wisepen_rag_graph_extraction` | 合并 | `wisepen_rag_v2_generation_cache` | 使用 `cache_kind` 区分，不再创建两个同构表和 protocol。 |
| `wisepen_rag_acl_projections` | 保留、修改 | `wisepen_rag_v2_resource_acls` | 本地 ACL 是在线 fail-closed 授权和后端同步的必要事实，但无需继续强调 projection 实现。 |

### 4.2 `resource_index_states`

每个资源恰好一条：

```text
resource_id                 unique
staged_content_revision     nullable
staged_document_version     nullable
applied_content_revision    nullable
applied_document_version    nullable
```

约束：

- staged 指针只在该 revision 的全部 Mongo 内容行写完后更新。
- applied 只能通过匹配 staged revision/version 的 CAS 更新。
- 读取能力先取 applied pointer，再读取对应 revision；无 pointer 时 fail closed。
- 不增加通用 `status/reason/error` 字段。staged/applied 两组明确指针已经表达完整状态。
- 暂不增加时间戳；只有真实的超时清理任务消费时才添加 staged/applied time。

### 4.3 `content_revisions`

```text
resource_id
content_revision            unique
document_version
content_hash
index_schema_version
structure_mode              sectioned | flat_text | empty
total_length
pages[]:
  page_index
  page_label
  start_offset
  end_offset
```

索引：

- unique `(content_revision)`。
- `(resource_id, document_version)`。

修改理由：

- `projection_mode` 改为业务真实名称 `structure_mode`。
- schema version 显式保存，便于解释 revision 和触发重建；不能只藏在 hash 算法常量中。
- `total_length` 在 index 时已经确定，直接保存，删除读取最后一个 content part 的额外查询。
- pages 作为轻量 revision 目录嵌入。即使数千页也远小于原文，且 structure/page read 都先读取 revision。

### 4.4 `source_parts`

```text
resource_id
content_revision
part_index
start_offset
end_offset
text
```

索引：unique `(content_revision, part_index)`，另加 `(resource_id, content_revision)` 供资源删除。

继续采用固定大小原文分片，保证超大 Markdown 不触碰 BSON 16 MB 限制。所有读取按 span 只加载覆盖的 part，不再为 page read 加载整篇原文。

### 4.5 `sections`

保留：

```text
resource_id
content_revision
section_id
title
level
parent_section_id
ordinal
section_path
preview
own_start
own_end
subtree_end
```

删除 `document_version`，因为它由 content revision 唯一确定，没有独立消费者。保留 `resource_id` 是为了 fail-closed 过滤和资源删除，不只是冗余复制。

索引：

- unique `(content_revision, section_id)`。
- `(content_revision, parent_section_id, ordinal)` 支撑 frontier。
- `(content_revision, own_start, own_end)` 支撑 page overlap 查询。
- `(resource_id, content_revision)` 支撑清理。

### 4.6 `reading_blocks`

```text
resource_id
content_revision
block_id
section_id
ordinal
raw_text
source_spans[]
start_offset
end_offset
page_labels[]
anchor_labels[]
```

`start_offset/end_offset` 是 source spans 的包围范围，供 page overlap 初筛；最终仍以 spans 判断，不能替代精确证据坐标。

索引：

- unique `(content_revision, block_id)`。
- `(content_revision, section_id, ordinal)`。
- `(content_revision, start_offset, end_offset)`。
- `(resource_id, content_revision)`。

ReadingBlock 保留 `raw_text`。虽然它可以从 source parts 重建，但 READ 高频使用且它就是稳定阅读单位；每次读取再拼 span 会制造不必要查询和一致性复杂度。

### 4.7 `source_refs`

```text
resource_id
content_revision
ref_id
chunk_id
reading_block_id
section_id
section_path[]
source_spans[]
page_labels[]
anchor_labels[]
```

修改：

- 新增 `reading_block_id`，使“RetrievalChunk -> SourceRef -> ReadingBlock”归属由权威 SourceRef 固化。v1 把 block ID 只放在 Qdrant，损坏 payload 时无法验证两者是否属于同一命中。
- 删除 `document_version`，由 revision 唯一确定。
- 保留 section path/page/anchor 的去规范化值，因为 evidence 响应真实消费这些字段；index 写入时必须校验它们与 Section/ReadingBlock 一致。

索引：

- unique `(content_revision, ref_id)`。
- unique `(content_revision, chunk_id)`，一个 RetrievalChunk 只能有一个 SourceRef。
- `(content_revision, reading_block_id)`。
- `(resource_id, content_revision)`。

### 4.8 `generation_cache`

```text
resource_id
cache_kind                  contextual_text | graph_candidates
cache_key
payload
```

索引：unique `(resource_id, cache_kind, cache_key)`。该复合索引以 `resource_id` 为前缀，也满足按资源删除的查询，不重复创建无独立消费的单字段索引。

所有缓存限定在资源内，不保留 v1 graph cache 仅按 extraction key 全局查询的隐式跨资源复用。这样资源物理删除能完整清理私有派生数据，不会因为另一资源碰巧使用同一输入 hash 而留下归属不清的 payload。该变化只牺牲跨资源缓存命中率，不改变 RAG 能力结果。

### 4.9 `resource_acls`

```text
resource_id                 unique
acl_revision
owner_id
readable_users[]
excluded_read_users[]
group_acls[]:
  group_id
  is_readable
  readable_users[]
  excluded_read_users[]
```

保留嵌套 group ACL，因为它与资源 ACL 同 revision、同写入周期，并且总是作为整体授权事实读取。没有独立查询或生命周期，不拆表。

旧 acl revision 不能覆盖新 revision。批量读取未命中的资源一律视为不可访问，不能即时回源后默认放行。

## 5. Qdrant 设计

### 5.1 collection

保留一个同时包含 dense 与 native BM25 sparse vector 的 collection：

```text
wisepen_rag_v2_retrieval_chunks
```

不拆成 dense/BM25 两个 collection。它们描述同一个 RetrievalChunk，需要相同 resource、revision、ACL 和 SourceRef 身份，拆分只会增加跨 collection 对齐。

### 5.2 payload

保留：

```text
resource_id
content_revision
active
chunk_id
reading_block_id
section_id
raw_text
section_path[]
anchor_labels[]
source_ref_id
embedding_key
acl_revision
owner_id
readable_users[]
excluded_read_users[]
group_acls[]
```

删除 `chunk_index`：当前 locate、rerank、verify 和删除均不消费它。排序身份由 chunk ID 和 score 决定，原文顺序由 ReadingBlock/SourceRef 负责。

新增 `active`：

- staged points 先以 `active=false` 写入。
- Mongo applied CAS 成功后激活当前 revision，并停用/删除旧 revision。
- CandidateSearch 必须过滤 `active=true`。
- verify 仍以 Mongo applied revision 做最终校验；`active` 是召回侧发布标记，不成为第二权威 revision。
- 文档事件重试必须能补偿“Mongo 已 applied、Qdrant 尚未 active”的中断窗口。

只为实际过滤字段创建 payload index：resource ID、content revision、active、embedding key、acl revision 和 ACL 条件字段。chunk/section ID 当前不在 Qdrant 中过滤，不创建无消费索引。

### 5.3 读写边界

保留 Qdrant 读写 adapter 分离：

- `QdrantRetrievalIndexWriter` 实现 `RetrievalIndexWriter`。
- `QdrantCandidateSearch` 实现 `CandidateSearch`。

两者共享私有 schema/payload 定义，但不能互相调用。写侧负责 collection 生命周期，读侧只查询并严格映射 payload。这是值得保留的 v1 仓储责任边界。

## 6. Neo4j 设计

### 6.1 namespace

v2 shadow 期间不得与 v1 共用同一组 labels/constraints：

- 优先使用独立 Neo4j database。
- 部署不支持多 database 时，使用 v2 专属 labels、constraint 名和带 v2 前缀的 node/edge ID。

不能在 v1 ResourceNode 上直接添加 v2 字段。

### 6.2 保留的图实体

节点：

- `ResourceNode`：资源、当前图 revision 和 ACL 入口。
- `EntityNode`：规范化实体，包含 label 与 entity type。
- `ExternalSourceNode`：文档外部来源。
- `ResourceGroupAcl`：Neo4j 无法以原生 property map 表示每群组 ACL，独立节点有真实查询需要，予以保留。

关系：

- `KNOWLEDGE_RELATION`：有 evidence 的知识关系。
- `MENTIONS`：资源证据与知识节点的连接。
- `HAS_GROUP_ACL`：ResourceNode 到 group ACL。

不新增 Graph、Projection、Extraction、Evidence 节点。当前查询不需要这些实体，revision 和 evidence 身份应作为资源/关系属性存在。

### 6.3 ResourceNode 发布字段

把 v1 的 `content_projection_revision`、`applied_relation_revision`、`skipped_content_revision` 收敛为：

```text
content_revision
graph_status                building | published | skipped
graph_revision              nullable
```

- 开始构建：写 content revision、`building`、清空 graph revision，使旧图立即不可见。
- 构建完成：CAS content revision，写 graph revision 和 `published`。
- flat/empty：CAS content revision，清旧图，写 `skipped`。
- GraphTraversal 和 MentionLookup 只读取 `published` 且 relation/mention revision 与 ResourceNode 一致的数据。

这是固定状态机，使用枚举语义。不得重新拆成多个可互相矛盾的 nullable 标记。

### 6.4 节点与关系字段

`KNOWLEDGE_RELATION` 保留：

```text
edge_id
relation_type
predicate
evidence_resource_id
evidence_quotes[]
evidence_source_ref_ids[]
source_content_revision
graph_revision
```

`MENTIONS` 保留并修改：

```text
mention_id
reading_block_id            # 替代含糊的 parent_id
source_ref_ids[]
evidence_quote
evidence_resource_id
source_content_revision
graph_revision
```

删除固定的 `origin='extracted'`。v2 当前只有抽取关系，没有消费者按 origin 分支；若以后出现人工关系或外部关系，再根据真实查询增加来源枚举。

保留 evidence quote 与 SourceRef ID：quote 是关系的精确断言证据，SourceRef 是回到权威 Markdown 的身份。二者不能互相替代，写入前必须由 index 校验 quote 确实落在对应 SourceRef 原文中。

### 6.5 读写 adapter

- `Neo4jKnowledgeGraphWriter` 实现 `KnowledgeGraphWriter`。
- `Neo4jMentionLookup` 实现 `MentionLookup`。
- `Neo4jGraphTraversal` 实现 `GraphTraversal`。
- `Neo4jGraphAclWriter` 实现 `GraphAclWriter`。

它们可以共享私有 Cypher schema 和 ACL predicate builder，但不能合成一个暴露所有方法的仓储。写图、发现入口、路径探索、ACL 同步属于四个 application owner。

## 7. Redis Navigation State

### 7.1 合并三类 key

v1 为一个 state 使用主 hash、known node set、known section hash 三个 key，存在 TTL 不一致和 `exists -> update` 竞态。v2 改为每个 state 一个 hash：

```text
key: wisepen:rag:v2:navigation:{state_id}

meta:user_id
meta:session_id
meta:root_query
section:{section_id}         JSON {resource_id, content_revision}
node:{node_id}               1
```

整个 key 使用统一 TTL。

### 7.2 原子语义

- create 用单条事务写入完整初始 state 并设置 TTL。
- add sections/nodes 使用 Lua 或等价原子操作：主 key 不存在时直接抛出 state-not-found，不能先 `exists` 再产生孤立字段。
- 每次成功访问是否续期由 navigation state 契约统一决定，不能只续期某些子 key。
- known Section 同时保存 resource ID 与被发现时的 content revision；READ 仍需校验当前 applied revision，revision 已变化时不能沿用旧发现权限。
- 不新增 resource-to-state 反向索引。资源删除、ACL 撤销和 revision 更新通过每次 READ/EXPAND/VERIFY 的最终校验立即失效；TTL 负责回收 Redis 数据。

保留 Redis 作为 state store，因为 TTL、原子集合扩展和短生命周期与 Mongo 内容事实不同。不能为了少一个后端把 navigation state 塞进 Mongo。

## 8. 权威 ACL 数据源

Java Resource Mongo 的 `wisepen_resource_items` 是外部权威表：

- v2 只读，不迁移、不改 schema、不把它声明为 RAG 自有 collection。
- `AuthoritativeAclReader` 独立连接上游 database，并返回 ACL 领域事实。
- `ResourceAclStore` 只连接 v2 database，不允许一个 repository 根据方法切换两个 database。
- ACL 事件流程明确为：读取权威事实 -> 计算 RAG ACL -> upsert 本地 ACL -> 显式同步 Qdrant -> 显式同步 Neo4j。
- 任一步失败直接抛出，由 Kafka 重试；不保存 `reason` 再向上传递。

## 9. 发布、一致性与删除

### 9.1 内容发布顺序

```text
1. ResourceIndexWriter 写完整 staged revision 数据
2. RetrievalIndexWriter 写 active=false 的 Qdrant points
3. ResourceIndexWriter CAS 发布 applied revision
4. RetrievalIndexWriter 激活当前 revision并清理旧 points
5. KnowledgeGraphWriter 构建并发布或跳过当前图
6. 清理旧 Mongo revisions
```

规则：

- 任意步骤失败都抛出，Kafka 重试相同事件必须收敛。
- 重试看到 Mongo 已 applied 时，仍要补偿 Qdrant active 标记、旧 points 清理和图发布，不能直接返回成功。
- READ/VERIFY 只认 Mongo applied revision。
- LOCATE 先用 Qdrant active 过滤，VERIFY 再核对 Mongo applied revision。
- EXPAND 只认 ResourceNode 的 published graph revision，并在回源时核对 Mongo applied revision。

不新增 saga、outbox、index task 或 error collection。现有事实事件、resource index state 和各后端幂等 revision 足以恢复；没有消费者的数据表不应提前创建。

### 9.2 资源删除顺序

资源删除由 `index` 用例显式编排，不使用通用 deletion target：

```text
1. 清除 resource_index_states 的 applied/staged 指针，使所有内容读取立即 fail closed
2. 删除 Qdrant points
3. 删除 Neo4j 关系、mention、ResourceNode、group ACL 和孤立节点
4. 删除 Mongo revision、source parts、sections、blocks、refs、generation cache
5. 调用 acl 删除本地 resource ACL
```

第一步完成后，其余后端可以通过 `asyncio.TaskGroup` 并行清理；任一失败由 ExceptionGroup 直接抛出并触发重试，不创建 errors/reasons 列表向上传导。

所有 v2 内容行都保存 resource ID，因此即使 state 已被删除，重试仍能按 resource ID 清理，不依赖先查询 revision 指针。

Redis state 不主动扫描删除。由于每次 READ/EXPAND/VERIFY 都重新校验 ACL 和 revision，旧 state 不能继续读取，随后由 TTL 回收。

## 10. 实现布局

建议 port 归属：

```text
domain/repositories/resource_index_writer.py
domain/repositories/applied_structure_reader.py
domain/repositories/applied_content_reader.py
domain/repositories/graph_build_source_reader.py
application/rag/locate/ports.py
application/rag/expand/ports.py
application/rag/verify/ports.py
application/rag/acl/ports.py
```

如果单个文件明显过大，可以按具体事实拆成 `content_store.py`、`graph_writer.py` 等，但不能创建每个目录都有的模板化 `repositories.py/models.py/services.py`。

建议 adapter 布局按后端和事实命名：

```text
persistence/mongo/resource_index_writer.py
persistence/mongo/applied_structure_reader.py
persistence/mongo/applied_content_reader.py
persistence/mongo/graph_build_source_reader.py
persistence/mongo/evidence_reader.py
persistence/mongo/generation_cache.py
persistence/mongo/resource_acl_store.py
persistence/mongo/authoritative_acl_reader.py
persistence/qdrant/retrieval_index_writer.py
persistence/qdrant/candidate_search.py
persistence/neo4j/knowledge_graph_writer.py
persistence/neo4j/mention_lookup.py
persistence/neo4j/graph_traversal.py
persistence/neo4j/graph_acl_writer.py
persistence/redis/navigation_state_store.py
```

Mongo adapter 使用 `domain/entities` 中的 Beanie Document；同后端 adapter 可以共享私有 serialization 和 query helper，但共享代码不能反向成为 application 的 `common` 模块。

Mongo 持久化映射的共享职责固定为：`core/persistence/mongo/mappers/serializer.py` 负责领域事实到 Mongo 字段的序列化，`core/persistence/mongo/mappers/deserializer.py` 负责 Mongo Entity 或上游记录到领域事实的反序列化。内容映射与 ACL 映射都遵循这两个文件的统一布局；仓储文件只负责查询、写入和删除，不重复实现字段转换。`domain/services/text_assembler.py` 负责 SourcePart 连续覆盖校验和文本组装，`SourcePartReader` 负责分片查询。不得在 Mongo 目录恢复同时包含 serializer、deserializer 和文本业务规则的 `content_records.py`，也不得用无仓储归属的 `source_text.py` 承载跨 reader 查询。

## 11. 明确禁止

- 禁止恢复 `ResourceSnapshotRepository`，或把 structure/page/section 再塞回 snapshot result。
- 禁止建立 `ProjectionRepository`、`DerivedRepository`、`SourceRepository` 等无法判断具体事实的仓储。
- 禁止 persistence/import domain repository 后再让 domain repository TYPE_CHECKING import application model。
- 禁止让 repository 组装 SectionView、Agent payload、错误 reason 或平台响应包装。
- 禁止让 Qdrant/Neo4j ACL adapter 自行解释权限规则；它们只执行 `acl` 提供的同一语义。
- 禁止把 GraphRAG 候选缓存当成已发布知识图谱。
- 禁止把 Qdrant payload 当权威正文或 SourceRef；最终证据始终来自 Mongo applied revision。
- 禁止把 Redis navigation state 当授权缓存。
- 禁止仅为了 repository 数量少而合并不同 owner 的 port，也禁止仅为了文件对称而为每张表创建 repository。

## 12. 迁移验收

- 六个 application 能力只依赖本能力拥有或明确公开的 port。
- v1 `domain/repositories` 中反向引用 application model 的路径全部消失。
- 10 个 v1 Mongo collection 按本文档收敛为 8 个 v2 collection，pages 与两类 generation cache 的迁移结果可核对。
- Qdrant staged/active/retry 流程覆盖崩溃恢复测试。
- Neo4j building/published/skipped 状态机覆盖 sectioned/flat/empty 转换和并发 revision 测试。
- Redis 单 key state 的 create/load/add/expire 全部具有原子测试。
- ACL 真值表同时验证本地 Mongo、Qdrant filter、Neo4j predicate 和最终回源。
- 资源删除在每个后端单独失败后重试均能完整收敛。
- v1/v2 对照确认检索、READ、EXPAND、VERIFY 和权限结果无未解释漂移后，才允许切流。
