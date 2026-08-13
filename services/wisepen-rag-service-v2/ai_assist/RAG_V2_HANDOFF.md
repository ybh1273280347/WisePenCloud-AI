# WisePen RAG v2 会话交接文档

本文档用于新会话接手 `wisepen-rag-service-v2` 迁移。内容以当前工作树和 `codex/rag-v2` 分支实际提交为准，不以 v1 文件名推断 v2 职责。

## 1. 工作位置

```text
worktree: D:\WisePenCloud-AI\WisePenCloud-AI-rag-v2
service:  services/wisepen-rag-service-v2
branch:   codex/rag-v2
remote:   dev
base:     origin/main @ e1af497f7
```

不要修改 `D:\WisePenCloud-AI\WisePenCloud-AI-formal_pr` 工作树。它只用于只读排查 v1 行为。

## 2. 已完成 Checkpoint

| 阶段 | Commit | 实际结果 |
|---|---|---|
| CP00 | `34e33ca9b` | 固化 Architecture、Repo、TODO、Migration，明确六个 application/rag 能力和迁移顺序。 |
| CP00.1 | `07d8b34da` | 建立物理隔离的 v2 服务目录和基础包骨架。 |
| CP01 | `4040b7410` | 迁移稳定 utils 与 core/config，补依赖；剔除 `presets`，不让旧预设约束 v2。 |
| CP02 | `1ece2ae3c` | 建立 `SourceSpan`、PageRange、Section、DocumentStructure 和 Markdown 结构解析。 |
| CP03 | `e828074e7` | 建立确定性的 ReadingBlock，支持 sectioned、flat_text、page/anchor/source span 归属。 |
| CP04 | `bb9d48fec` | 建立 RetrievalChunk、SourceRef、稳定身份和归属校验。 |
| CP05 | `6adf3d79d` | 建立 revision、原文分片、staged/applied 决策和 CAS 语义。 |
| CP06 | `6cbf53716` | 持久化 Section、ReadingBlock、SourceRef，支持资源清理和图构建输入读取。 |
| CP06.1 | `3e8241c71` | 引入 Beanie entities、domain repositories，revision 规则改名为 `index/revisions.py`。 |
| CP07 | `57befb093` | 完成无状态 READ：structure、pages、sections、frontier、ReadingBlock 顺序。 |
| CP06.2 | `0ce994168` | 删除错误的双轨 persistence 构造；Mongo adapter 不再接受 `database` 参数或 `_BeanieCollection`。 |
| CP08 | `81a47997e` | VERIFY 回源闭环。 |
| CP08.1 | `79c350634` | 拆分 index 写入、结构获取、正文获取和图构建输入读取边界。 |
| CP08.2 | `634c4d24f` | 拆分 Mongo 内容映射、SourcePart 文本组装和分片查询职责。 |
| CP08.3 | `9d0a1bc46` | 将持久化映射器从 domain 移回 Mongo persistence，并收敛为 serializer/deserializer 两个文件。 |
| CP08.4 | `a8eeaaef6` | 将 Beanie 内容实体模块从 `content_index.py` 重命名为 `rag_content.py`。 |
| CP09 | `b16b7d630` | ACL 领域规则、READ/ACL 面向对象用例和 dependency-injector 容器装配。 |
| CP10 | `06d46fb3d` | 上游权威 ACL reader、本地 Beanie ACL store、revision 幂等 upsert 和资源删除。 |
| CP10.1 | `fb931795e` | 将 ACL 的 Mongo 序列化/反序列化统一收敛到现有 `mappers/serializer.py` 与 `mappers/deserializer.py`。 |
| CP11 | `df411431c` | 合并为单一 generation cache collection，按资源和 cache kind 批量读写及删除。 |
| CP12 | `c5113eb44` | Contextual indexing 生成、严格响应解析、缓存复用和只增强 `index_text`。 |
| CP13 | `21ac955f8` | Qdrant retrieval index 的 staged/active revision 写入、向量复用、旧 revision 清理和资源删除。 |
| CP14 | `20c13cd3a` | Qdrant dense/BM25 混合候选召回、active/resource/ACL 过滤和最小候选映射。 |
| CP15 | `86d7f888` | Redis 单 hash navigation state、统一 TTL 和 Lua 原子扩展。 |
| CP15.1 | `537c52265` | Redis navigation state 曾将映射收敛到 persistence/mappers。 |
| CP15.2 | `a571def8` | 纠正过度集中映射：Mongo 按 readers/writers 组织并私有映射，Redis/Qdrant 映射直接内联。 |
| CP16 | `417962e8` | LOCATE 主链：混合召回、最终 ACL/revision 过滤、应用层排序、VERIFY 回源和阅读入口状态。 |
| CP16.1 | `85679b1a` | 将 VERIFY 证据校验改为注入式 `EvidenceVerifier`。 |
| CP17 | `06f98b6d` | GraphRAG 窗口抽取、连续 evidence 校验、候选缓存及 cache 重校验。 |
| CP18 | `4bb407d5` | NFKC/大小写规范化、节点/关系/evidence 合并、MENTIONS 和稳定 graph revision。 |
| CP19 | `4d39d2dc` | Neo4j v2 namespace、KnowledgeGraphWriter 和 building/published/skipped CAS 发布状态机。 |
| CP19.1 | `693296c9` | 将知识关系稳定身份统一为 Repo.md 冻结的 `edge_id`。 |
| CP20 | `a9c2e06d` | MentionLookup 按已核验 SourceRef、published graph、revision 和 ACL 发现初始节点并写入 navigation state。 |
| CP21 | `4a3e5961` | EXPAND 有界图遍历、路径排序、逐边 VERIFY 和并发安全的 known node 原子扩展。 |
| CP22 | `8e05be98` | 有状态 Section READ：state/ACL/revision 校验、完整正文读取与 frontier 原子扩展。 |
| CP23 | `7e3a1a224` | 权威 ACL 刷新、本地单调写入、Qdrant/Neo4j 显式同步和统一图查询 predicate。 |
| CP24 | `cb73b1a57` | ResourceIndexer 编排结构、contextual、embedding、Mongo/Qdrant 发布、图 publish/skip 和重试补偿。 |
| CP25 | `ae9b0c44d` | 先清 Mongo 发布指针 fail closed，再并行删除内容、缓存、Qdrant、Neo4j 和本地 ACL。 |
| CP26 | `e285530b0` | 确定性 document structure/page/section READ HTTP schema、统一 ACL 和资源读取错误码。 |
| CP27 | `98b0e3555` | LOCATE、发现后 Section READ、EXPAND HTTP schema、可信身份与导航错误映射。 |
| CP28 | `c6888c42e` | 三类 Kafka adapter、保序 offset 重试、显式运行时配置与服务生命周期装配。 |
| CP29 | 当前工作树 | 集成门、稳定事实 golden、shadow 差异审批工具、回放/切流/回滚 runbook，并修复 HTTP 错误码与 LOCATE seed 返回闭环。 |

## 3. 当前架构事实

### Application 六个目录

```text
application/rag/index/
application/rag/locate/
application/rag/read/
application/rag/expand/
application/rag/verify/
application/rag/acl/
```

- `index`：构建并发布所有派生数据。
- `locate`：召回和发现阅读入口、建立导航状态。
- `read`：读取结构、page、Section 和正文。
- `expand`：从已发现图节点做有界关系探索。
- `verify`：把候选结果回到 applied revision 的权威证据。
- `acl`：定义和执行权限规则。

RAG 不生成 Agent 的 `page_not_found`、`section_not_found`、`section_empty`、展示文案或探索原因；这些由调用方装配。

### Domain 与 persistence 约定

- Mongo Document 必须放在 `domain/entities`，当前为 `rag_content.py` 中的 RAG 内容 Beanie entities。文件名不使用 `index`，避免与 `application/rag/index` 的写入能力混淆。
- repository port 必须放在 `domain/repositories`。
- `application` 只依赖语义 port，不依赖 Mongo Document 或 driver 对象。
- Mongo adapter 只有一条构造路径：依赖已完成 `init_beanie` 的 Document 类。
- 禁止重新引入 `database: AsyncDatabase | None`、fake collection 注入、`_BeanieCollection` 或兼容旧测试的双入口。
- staged/applied 指针的条件更新可以在 adapter 内部使用对应 Beanie entity 的底层 collection 完成原子 CAS；这不是第二套构造路径。

### 内容不变量

- Markdown 是正文和证据坐标的唯一权威来源。
- offset 是 Python 字符下标，区间为左闭右开。
- 只有完整写入后才发布 staged/applied 指针。
- `locate/read/expand/verify` 只能读取 applied revision。
- SourceRef 必须能回到 ReadingBlock、Section 和原文 span。
- contextual text 不能修改 raw text、source span 或 SourceRef。

## 4. 当前 CP08 实现

### Domain

文件：`src/rag/domain/evidence.py`

- `EvidenceCandidate`：调用方提供的 resource、revision、SourceRef ID 和候选 RetrievalChunk。
- `EvidenceRecord`：VERIFY 返回的权威 revision、SourceRef、ReadingBlock、Section 和原文。
- `EvidenceNotFoundError`、`EvidenceRevisionError`、`EvidenceCorruptError`：失败直接抛出。

### Port

文件：`src/rag/domain/repositories/evidence_reader.py`

```python
read_applied_evidence(
    resource_id,
    content_revision,
    source_ref_ids,
) -> dict[str, EvidenceRecord] | None
```

### Application

文件：`src/rag/application/rag/verify/evidence.py`

`EvidenceVerifier.verify()` 会校验：

- 一批候选必须属于同一 resource/revision。
- SourceRef ID、chunk ID、ReadingBlock ID、Section ID 和 section path。
- source spans、page labels、anchor labels。
- candidate raw text 与权威回源文本。

### Mongo adapter

文件：`src/rag/core/persistence/mongo/evidence_reader.py`

- 读取当前 applied revision。
- 重建完整 source parts。
- 用 SHA-256 校验重建原文与 `ContentRevision.content_hash`。
- 读取 SourceRef、ReadingBlock、Section 并组装 `EvidenceRecord`。
- 缺失 part、SourceRef、Block、Section 或 revision 不一致时直接抛出。

## 5. 当前验证

CP29 完整源码门禁：

```text
uv run --project services/wisepen-rag-service-v2 pytest -q
  -> 170 passed, 1 个 Nacos 依赖弃用 warning
uv run --project services/wisepen-rag-service-v2 ruff check src tests scripts
  -> All checks passed
uv run --project services/wisepen-rag-service-v2 python -m compileall -q src scripts
  -> passed
git diff --check -- services/wisepen-rag-service-v2
  -> passed
```

测试覆盖：

- index revision identity 和 stage decision。
- READ 缺失 applied revision 直接失败。
- VERIFY 正常回源。
- 缺失 SourceRef。
- chunk 与 SourceRef 身份不一致。
- revision 不一致。

CP29 新增六类稳定事实 golden、未批准差异阻断、跨领域/Qdrant/Neo4j ACL 契约和 HTTP 业务错误码测试。真实 Mongo/Qdrant/Neo4j/Redis 环境回放与 v1/v2 shadow 尚未执行，不能把源码门禁解释为生产对照通过。

## 6. 当前工作树状态

CP00-CP28 均已作为独立 checkpoint 提交并推送。当前工作树只包含 CP29 集成门，提交后应停止在真实环境回放与调用方迁移审批点。

CP08.1 的稳定边界：

- `ResourceIndexWriter` 只负责 stage、apply、delete；CAS 所需状态读取留在 adapter 内部。
- `AppliedStructureReader` 只获取 applied document structure。
- `AppliedContentReader` 只获取 page/Section 正文和 frontier。
- `GraphBuildSourceReader` 只为 index 图构建阶段读取指定 revision 的输入。
- `index/structure.py` 构建结构事实，`read/structure.py` 获取已发布结构。
- READ application 动作统一为 `get_document_structure`、`get_pages`、`get_sections`。

CP08.2 的稳定边界：

- Mongo reader/writer 按 `core/persistence/mongo/readers/` 与 `writers/` 组织，读写 store 保留在 Mongo 根目录。
- 字段映射默认私有内联：reader 使用 `_to_domain()`，writer/store 使用 `_to_document()`；少量重复不抽成全局 mappers。
- 只有至少两个 Mongo adapter 真实复用同一序列化契约时才允许增加 `shared_serializers.py`，当前没有满足条件的转换。
- `domain/services/text_assembler.py` 只负责 SourcePart 长度、重叠、间隙和连续覆盖校验，以及原文组装。
- `SourcePartReader` 和 `MongoSourcePartReader` 只负责 SourcePart 查询，不负责文本组装。
- `content_records.py`、`source_text.py` 已删除；Mongo reader 不再通过 `model_dump()` 字典进入领域映射或文本组装。
- 领域层不再知道 `start_offset`、`end_offset` 等 Mongo 持久化字段名。

```text
ai_assist/RAG_V2_HANDOFF.md
src/rag/domain/evidence.py
src/rag/domain/repositories/evidence_reader.py
src/rag/application/rag/verify/evidence.py
src/rag/application/rag/verify/__init__.py
src/rag/core/persistence/mongo/evidence_reader.py
src/rag/core/persistence/mongo/__init__.py
tests/rag/test_index_contracts.py
```

提交前必须重新运行测试、目标 lint、compileall、`git diff --check`，只提交上述 v2 路径和必要的根 `uv.lock`。

## 7. 下一步任务

源码迁移顺序已到 CP29 末尾。下一步不是继续增加 application 实体或仓储，而是按 `Runbook.md` 准备独立 v2 后端、脱敏文档/query/身份集和调用方适配，然后执行 `Shadow.md` 的真实对照审批。未经审批不得实际切流、停止 v1 consumer 或删除 v1 数据。

CP11 的稳定边界：

- `GenerationCacheEntity` 统一承载 `contextual_text` 与 `graph_candidates` 两类字符串 payload。
- `GenerationCacheStore` 只按 resource、cache kind 和 opaque cache key 做批量 get/set/delete。
- cache key 的 prompt、schema、model、input 配方由对应的生成 application 自己拥有，不下沉到通用缓存仓储。
- generation cache 是 RAG 派生数据；资源删除必须按 resource ID 清理全部 cache kind。
- `container.py` 只声明 `contextual_text_client` dependency；配置中心和 LLM client 的实际创建留给服务启动组合层，避免导入容器时触发 Nacos。

CP12 的稳定边界：

- `ContextualTextIndexer` 位于 `application/rag/index`，只处理结构化 revision 的 RetrievalChunk。
- `flat_text` 和 `empty` revision 直接跳过，不调用模型、不写 contextual cache。
- 模型输入由 section path、Section preview、所属 ReadingBlock 原文和目标 chunk 原文组成；响应必须是带非空 `contextual_text` 字符串的 JSON 对象。
- 成功结果只通过 `RetrievalChunk.with_contextual_text()` 增强 `index_text`；raw text、source spans、page/anchor labels 和 SourceRef 身份不变。
- 生成异常直接抛出；不写入空值、错误字符串或 reason 列表。

CP09 已完成：

- `PermissionScope`、`ResourceAcl`、`GroupResourceAcl` 等最小权限事实。
- owner、直接用户、资源排除、managed group、joined group 规则。
- 单资源 authorize 和批量 readable resource 计算。
- Qdrant/Neo4j 可消费的统一权限表达输入。
- `PermissionAuthorizer`、`DocumentStructureReader`、`DocumentContentReader` 及其依赖注入装配。
- 完整 ACL 真值表和 fail-closed 测试。

CP09 已明确排除：

- Mongo ACL adapter。
- Qdrant/Neo4j ACL 同步。
- HTTP、Kafka、Agent 业务语义。
- 修改 VERIFY 的证据校验。

后续顺序仍以 `Migration.md` 为准：CP20 MentionLookup/LOCATE 节点入口，CP21 EXPAND，CP22 有状态 READ，CP23 ACL 同步，CP24 文档完成编排，CP25 删除编排，CP26-28 adapters，CP29 集成门。

CP17-19 图谱边界：

- `index/graph_extraction` 只负责窗口、GraphRAG 候选和确定性校验；缓存保存候选，不等于已发布图。
- `index/graph_merge.py` 只负责节点规范化、等价合并、关系/evidence 去重、MENTIONS 和 graph revision，不使用 `projection` 命名。
- `domain/knowledge_graph.py` 中的 `KnowledgeGraph` 是 CP19 写入 port 的输入事实，不是 Neo4j document，也不承载 Agent 展示语义。
- `domain/repositories/knowledge_graph_writer.py` 只暴露 schema 初始化、begin build、publish、skip、delete；状态查询不混入写入 port。
- `core/persistence/neo4j/knowledge_graph.py` 使用 v2 专属 labels、关系类型和 constraint。所有发布先校验 `document_version`/`content_revision`，最后 CAS 标记 `published` 或 `skipped`；旧 revision 直接抛出 `KnowledgeGraphRevisionSupersededError`。

CP20 节点入口边界：

- `locate/ports.py` 的 `MentionLookup` 只从 VERIFY 已核验的 `EvidenceRecord` 发现图节点，不新增 SourceRef 包装模型。
- `Neo4jMentionLookup` 先调用统一 `PermissionAuthorizer`，再查询当前 `published` graph；不在 Neo4j adapter 内复制 ACL 规则。
- `ReadingEntryLocator` 只把稳定 node ID 写入 `NavigationState.known_node_ids`，不改变 LOCATE 面向调用方的 Section/evidence 返回契约。

CP21 EXPAND 边界：

- `expand/ports.py` 的 `GraphTraversal` 只查询 node、edge、path 与 evidence SourceRef 身份，不排序、不读取正文、不修改 state。
- `Neo4jGraphTraversal` 只使用固定方向/深度 pattern，并要求 evidence resource 的 graph 仍为当前 `published` revision；统一 ACL 在返回前复查。
- `KnowledgeGraphExpander` 校验 state 用户/session 与 seed 白名单，按请求 query 或 root query 排序，逐 edge 调用 `EvidenceVerifier.verify_refs()`，最后原子扩展 known nodes。
- `NavigationStateStore.add_known_nodes()` 返回本次原子操作实际新增的 node IDs；并发调用只允许一个结果返回对应新路径，不使用 `get -> compare -> add`。
- EXPAND 返回领域 node、edge、path 和权威 `EvidenceRecord`，不组装 HTTP/MCP/Agent 文案。

CP22 已发现 Section 展开边界：

- `DiscoveredSectionExpander` 只展开 navigation state 中已经发现的 Section；无状态 `DocumentContentReader` 的 page/Section 行为不变。
- state 必须匹配当前 user/session；未知 Section 直接抛 `SectionNotDiscoveredError`，不静默扩大读取范围。
- 正文查询前后各执行一次统一 ACL 与 applied revision 校验，读取期间发生撤权或 revision 切换时 fail closed。
- `AppliedContentReader` 返回完整 `SectionContent` 后，parent/previous/next/children 使用现有 `add_known_sections()` 原子加入同一 state。

CP23 ACL 同步边界：

- `ResourceAclRefresher` 读取上游权威 ACL、单调写入本地 store，再显式同步 Qdrant 与 Neo4j；后端失败通过 `TaskGroup` 直接抛出。
- 本地已有相同 revision 时仍同步两个后端以补偿此前失败；本地 revision 更高时忽略旧事件，禁止旧 ACL 覆盖。
- `QdrantRetrievalAclWriter` 与 `Neo4jGraphAclWriter` 只序列化统一 `ResourceAcl`，不自行解释权限规则。
- Neo4j `acl_predicate()` 与 `ResourceAcl.can_read()` 保持 owner、直接用户、资源排除、managed/joined group 语义一致；MentionLookup/GraphTraversal 下推 predicate 后仍保留最终 `PermissionAuthorizer` 复查。
- ACL 可以先创建 ResourceNode；KnowledgeGraphWriter 的首次 begin build 允许 `document_version IS NULL`，不会被 ACL 同步反向阻断。

CP24 文档索引编排边界：

- `ResourceIndexer.index_resource()` 是一次文档完成事件的唯一应用层编排对象，不增加流程 DTO、task 表、saga 或错误原因字段。
- Mongo stage 先完成 stale 判断；只有非 stale 事件继续 contextual text、ACL 刷新、向量复用/生成和跨后端发布。
- 发布顺序固定为 Mongo stage、Qdrant staged、Mongo applied CAS、Qdrant activate/cleanup、Neo4j publish/skip、Mongo 旧 revision 清理。
- `ALREADY_APPLIED` 重试不会提前返回，仍补偿 Qdrant 和 Neo4j；任一步真实失败直接抛出，由相同事件重试收敛。
- sectioned 文档抽取并发布知识图，flat_text/empty 明确 skip；三种结构均不创建伪图谱或额外状态实体。

CP25 资源删除编排边界：

- `ResourceDeleter` 先调用 `ResourceIndexWriter.clear_resource_states()` 清除 applied/staged 指针，保证后端物理清理开始前 READ/VERIFY 已 fail closed。
- 随后用 `TaskGroup` 并行删除 Qdrant points、Neo4j 图与 group ACL、Mongo 内容 revision、generation cache 和本地 ACL；任一失败直接抛出 `ExceptionGroup`。
- Mongo 内容删除按 `resource_id` 查询 revision，不依赖仍然存在的 index state，因此第一步已成功或 state 原本缺失时重试仍能收敛。
- Redis navigation state 不扫描删除；旧 state 在 applied revision 缺失后由 READ/EXPAND/VERIFY 拒绝，随后由 TTL 回收。

CP26 HTTP READ adapter 边界：

- `/resources/document-structure`、`/page-content`、`/section-content` 沿用内部服务路由惯例，使用 `R[...]`、`require_login` 和 dependency-injector 注入 application reader。
- `DocumentStructureReader` 与 `DocumentContentReader` 在 application 层统一执行 ACL；未授权与 applied 内容不存在都抛 `ContentNotFoundError`，HTTP 映射为同一 `RESOURCE_CONTENT_NOT_FOUND`。
- 批量 page/section 响应使用请求 key 到领域事实的字典，只返回实际存在 key；合法空 Section 返回 `reading_blocks=[]`，不生成 `kind/reason/windows`。
- schema 使用 list 而非 tuple，最多接收 20 个 page label 或 section ID，所有请求 `extra=forbid`；响应只序列化稳定结构、正文、offset、frontier 和锚点事实。
- 非预期 application/依赖异常映射为 `RESOURCE_READ_FAILED`，不把底层异常文本、存储结构或资源存在性泄漏给调用方。

CP27 HTTP Navigation adapter 边界：

- `locate`、`expandDiscoveredSections`、`expandGraph` 分别调用 `ReadingEntryLocator`、`DiscoveredSectionExpander` 和 `KnowledgeGraphExpander`，不恢复 v1 的聚合 service 或 cypher 命名。
- 请求 body 只包含 session、查询、state 和导航边界；`PermissionScope.user_id` 与群组角色始终来自 `require_login` 和 `SecurityContextHolder`，客户端不能伪造身份。
- locate 返回 state、相关性 decision、Section frontier 和已核验证据；expand 返回领域 node、edge、path 和 SourceRef 回源事实；不组装 Agent reason 或探索提示。
- 请求 schema 使用 list，Section 最多 12 个、seed/relation type 最多 16 个、depth 只允许 1/2、结果最多 20 个，所有请求 `extra=forbid`。
- state 不存在/过期/身份不匹配映射为 `NAVIGATION_STATE_NOT_FOUND`；撤权或 revision/evidence 失效映射为 `NAVIGATION_STATE_INVALIDATED`；未知 Section/seed 与输入错误映射为 `NAVIGATION_INVALID`；依赖失败映射为 `NAVIGATION_FAILED` 且不透传内部文本。

CP28 Kafka 与服务生命周期边界：

- Kafka adapter 校验 `resourceId/version/content`、`resourceId` 和 `typedResourceIds` 三类外部 payload，再分别调用 `ResourceIndexer`、`ResourceAclRefresher` 与 `ResourceDeleter`；application 不依赖 Kafka schema。
- 永久非法 JSON/schema payload 抛 `KafkaPayloadError` 并提交该条 offset；application 或依赖失败保留当前 offset，在同一消息上原地重试，成功后只提交一次，禁止后续 commit 越过失败事件。
- ACL 重算晚于资源删除到达时，`AuthoritativeAclNotFoundError` 作为终态 no-op；其余 ACL 同步失败仍重试。
- 配置读取从模块导入移到 lifespan：导入 `rag.main` 不拉 Nacos、不连接存储；运行时显式加载配置并注入容器，配置缺失直接阻止启动。
- lifespan 顺序为 Beanie、Qdrant、Neo4j schema/连接初始化，随后启动三类 consumer 和注册服务；任一步失败不会进入 ready，关闭时反向停止 consumer 并释放模型、Redis、Qdrant、Neo4j、Mongo 客户端。
- HTTP 使用运行时加载的内部来源密钥和 `SecurityContextHolder`，container wiring 只装配 resources/navigation endpoints；保留 `/health` 与 OpenAPI 文档。

CP13 的实现边界：

- `RetrievalIndexWriter` 位于 `domain/repositories`，只接收 `RetrievalChunk`、`SourceRef`、`ResourceAcl` 和 dense vector，不暴露 Qdrant 原生类型。
- `QdrantRetrievalIndexWriter` 位于 `core/persistence/qdrant`，负责 collection 创建、payload index、dense vector 复用、staged point 写入、revision 激活、旧 revision 清理和资源删除。
- Qdrant payload 的序列化和候选反序列化分别私有内联在实际 writer/search adapter 中，不建立 mappers 子目录。
- staged point 的 `active` 固定为 `false`；Mongo applied CAS 成功后由 `activate_revision()` 设置当前 revision 为 active，并关闭旧 revision 的召回可见性，随后由 `delete_other_revisions()` 清理旧 point。
- payload 保留 `resource_id`、`content_revision`、`active`、chunk/SourceRef 身份、原文检索字段、embedding key 和 ACL 字段；明确不写入 v1 的 `chunk_index`。
- native BM25 使用 Qdrant `Document(text=chunk.index_text, model="qdrant/bm25")`，dense vector 必须符合配置维度；缺失向量、SourceRef 或 revision 归属错误直接抛出。
- CP13 不实现 query embedding、rerank 或独立 ACL 同步；这些分别留给 CP16 和 CP23。

CP14 的实现边界：

- `CandidateSearch` 位于 `domain/repositories`，输入 `CandidateSearchRequest`，返回 `RetrievalCandidate` 列表；不返回 Qdrant Point、Record 或 driver 类型。
- `QdrantCandidateSearch` 只执行 dense/BM25 两路预取、Qdrant RRF 融合、`active=true`、资源白名单和 ACL 条件下推，并映射 locate/rerank 必需的最小 payload。
- `core/persistence/qdrant/acl_filter.py` 只把 `PermissionScope` 翻译成 Qdrant nested `group_acls` filter；授权规则仍以 `ResourceAcl.can_read()` 为领域语义来源。
- 缺少 collection 或 limit 非正时返回空 list；空 lexical query、空/错误维度 semantic vector、缺失或类型错误 payload 直接抛出。
- CP14 不负责 query embedding、应用层 rerank、ReadingBlock 去重、applied revision 核对、最终 ACL 复查、navigation state 或 Agent 结果装配。

CP15 的实现边界：

- `NavigationState` 与 `KnownSection` 位于 `domain/navigation.py`；Section 映射同时保存 `resource_id` 和发现时的 `content_revision`。
- `NavigationStateStore` 位于 `domain/repositories`，只暴露 create/get/add sections/add nodes，不暴露 Redis key、hash 或 Lua 类型。
- `RedisNavigationStateStore` 使用一个 `wisepen:rag:v2:navigation-state:<state_id>` hash；`known_sections` 和 `known_nodes` 作为 JSON 字段，避免 v1 多 key 结构产生孤立状态。
- Redis 状态的 hash/JSON 映射私有内联在唯一的 `navigation_state_store.py` 中，不建立 mappers 子目录。
- create 写入完整 hash 后设置统一 TTL；两个 add 操作用 Lua 原子检查主 key、合并集合并续期主 key，状态不存在直接抛出 `NavigationStateNotFoundError`。
- CP15 不实现 LOCATE/READ/EXPAND 用例、state 用户/session 校验或删除编排；这些由 CP16、CP22、CP21/CP25 的 application 负责。

CP16 的实现边界：

- `ReadingEntryLocator` 只编排 query embedding、Qdrant 候选、应用层 ranking、最终 ACL/applied revision 过滤、VERIFY 回源和 navigation state 创建。
- semantic query 只 embedding 一次；未提供 lexical query 时复用 semantic query，显式空 lexical query 直接抛出。
- ranking candidate identity 使用 `resource_id + content_revision + chunk_id`，不依赖 chunk ID 跨资源唯一；输出按 `(resource_id, reading_block_id)` 去重，同一 Section 可以保留多个 block 证据。
- `RELEVANT` 与 `UNCERTAIN` 返回已核验 Section 入口；`IRRELEVANT` 创建空 navigation state，且不回源 VERIFY。
- Qdrant payload 增加 `source_spans` 和 `page_labels` 供 VERIFY 比对；最终正文和结构仍来自 Mongo applied revision，结构 revision 在 VERIFY 后再次核对以拒绝并发切换。
- CP16 不装配 Agent/MCP 展示语义，不返回 reason/status 包装，不实现知识节点解析。

## 8. 接手禁区

1. 不要恢复 `snapshot`、`projection`、`ResourceSnapshotRepository` 等旧抽象。
2. 不要建立全局 `models.py`、`common.py` 或错误 reason/status 传递层。
3. 不要为了测试重新增加第二种 adapter 构造方式。
4. 不要把 Agent 探索语义塞回 RAG。
5. 不要把 Qdrant payload 或 Neo4j record 当权威正文。
6. 不要在一个 checkpoint 顺手跨越多个 application 能力。
