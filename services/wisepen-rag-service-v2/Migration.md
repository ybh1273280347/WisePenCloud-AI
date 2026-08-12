# WisePen RAG Service v2 迁移与 Checkpoint 顺序

本文档规定 v2 的实现顺序、每次提交范围和分支纪律。能力边界以 [Architecture.md](./Architecture.md) 为准，仓储与数据设计以 [Repo.md](./Repo.md) 为准，完整能力清单以 [TODO.md](./TODO.md) 为准。

目标不是尽快堆出一个可启动服务，而是让每个 checkpoint 都能独立审查、验证和回滚，避免一次重构跨越多个能力边界。

## 1. 分支与路径

```text
branch:   codex/rag-v2
worktree: D:\WisePenCloud-AI\WisePenCloud-AI-rag-v2
base:     origin/main @ e1af497f7e0666317b258c279befc6a8ec46efdf
scope:    services/wisepen-rag-service-v2/**
```

规则：

- 不切换、不提交、不清理持久 `formal_pr` 工作区；它只作为 v1 行为排查来源。
- v2 分支只提交 `services/wisepen-rag-service-v2/**`，依赖 checkpoint 允许同步根 `uv.lock`。旧 `services/wisepen-rag-service/**` 仅作为只读行为来源。
- Chat/Common/MCP 调整不进入该分支；真正切流需要调用方改动时另开对应边界提交。
- 每个 checkpoint 保留独立 commit，不 squash、不 amend 已交付 checkpoint。
- 分支始终以创建时记录的 `origin/main` 为评审基线，不继承 `formal_pr` 的混合历史。
- 未经明确请求不 push；需要推送时只推 `codex/rag-v2`。
- 每次提交前执行路径审计：

```powershell
git diff --cached --name-only
git diff --cached --stat
git diff --check -- wisepen-rag-service-v2
```

暂存区一旦出现 `services/wisepen-rag-service-v2/**` 和已声明的根 `uv.lock` 之外的路径，立即停止提交并排查。

## 2. Checkpoint 完成标准

每个 checkpoint 必须同时满足：

- 只解决表中列出的一个能力或一个持久化边界。
- 实现与该范围的测试在同一个 commit，不提交“后面再补测试”的半成品。
- 新增公开名称可以从名字判断动作和对象，不引入 snapshot/projection/materializer/manager 等旧抽象。
- 不为了后续 checkpoint 提前创建空 model、port、repository 或配置项。
- 当前已有测试继续通过；新增范围至少有正常、缺失/空值、一致性失败三个方向的针对性测试。
- Python checkpoint 通过目标测试、`compileall` 和目标目录 `git diff --check`。
- checkpoint 结束时工作树干净，commit message 使用：

```text
rag-v2 cpNN: <单一职责描述>
```

只有标为“集成门”的 checkpoint 运行全量 v2 测试；普通 checkpoint 只运行目标测试，控制单次反馈和修复范围。

## 3. 明确迁移顺序

### CP00：架构基线

范围：

- `Architecture.md`
- `Repo.md`
- `TODO.md`
- `Migration.md`

验收：四份文档互相引用、无冲突，分支只包含 v2 文档。

排除：任何 Python、配置、依赖或旧服务修改。

Commit：`rag-v2 cp00: establish architecture and migration baseline`

### CP01：稳定 Utils、配置与包骨架

范围：

- 完整迁移稳定 `utils`，但剔除 RAG v1 的 `ranking/presets.py`。
- 补齐 utils 和 core/config 实际导入的 project dependencies。
- 迁移稳定 `core/config`，并为服务名、Kafka group 和存储 namespace 使用 v2 默认值。
- 建立空的 API、六个 application/rag 能力、domain 和 persistence 包占位。
- 为纯 utils 增加最小 smoke tests。

验收：依赖锁可解析，utils smoke tests、ruff 和 compileall 通过，`presets.py` 不存在。

排除：FastAPI endpoint、application 实现、持久化实现、容器装配和任何 v2 RAG preset。

Commit：`rag-v2 cp01: migrate stable utilities and configuration`

### CP02：原文坐标与结构事实

范围：

- Python 字符左闭右开 `SourceSpan`。
- `StructureMode` 固定集合。
- Page range、Section 的最小跨能力事实。
- Markdown 标题、页标记、锚点到结构事实的纯函数解析。

验收：Unicode、嵌套标题、无标题、空文档、页标记 offset golden tests。

排除：ReadingBlock、RetrievalChunk、SourceRef、数据库和 API。

Commit：`rag-v2 cp02: define source coordinates and document structure`

### CP03：阅读块构建

范围：

- Section 到 ReadingBlock 的确定性拆分。
- sectioned 与 flat_text 的 ReadingBlock 规则。
- flat_text 6000 字符、无重叠父块。
- ReadingBlock page/anchor/source span 归属。

验收：长 Section、多 block、flat text、跨页与 Unicode 边界测试。

排除：RetrievalChunk、embedding、contextual indexing 和持久化。

Commit：`rag-v2 cp03: build deterministic reading blocks`

### CP04：检索块与 SourceRef 构建

范围：

- ReadingBlock 到 RetrievalChunk 的确定性拆分。
- flat_text 800 字符、100 字符重叠子块。
- RetrievalChunk、SourceRef、ReadingBlock 的稳定身份和归属校验。
- SourceRef 增加权威 `reading_block_id`。

验收：稳定 ID、chunk overlap、SourceRef 精确回源和错误归属测试。

排除：contextual text、向量、Mongo 和召回。

Commit：`rag-v2 cp04: build retrieval chunks and source references`

### CP05：Mongo revision 与原文存储

范围：

- `resource_index_states`、`content_revisions`、`source_parts` 三个 collection。
- stage decision、staged pointer、applied CAS。
- content hash、schema version、structure mode、total length、嵌入 page ranges。
- ResourceIndexWriter 的 revision/source 写入部分。

验收：首次 stage、重复 applied、stale event、同版本内容修正、CAS 冲突、超大原文分片测试。

排除：Section/Block/SourceRef collection、Qdrant 和图谱。

Commit：`rag-v2 cp05: persist content revisions and source parts`

### CP06：Mongo 结构与证据存储

范围：

- `sections`、`reading_blocks`、`source_refs` collection。
- ResourceIndexWriter 完整 revision 写入与资源清理。
- staged pointer 最后发布、不完整 revision 不可见。
- 按指定 applied revision 读取图构建输入。

验收：完整写入、写中断重试、资源清理、结构/块/ref 归属和索引测试。

排除：READ 用例、VERIFY 用例和外部后端。

Commit：`rag-v2 cp06: persist resource structure and evidence identities`

### CP06.1：Beanie entities 与 domain repositories

范围：

- 将 Mongo collection schema 固化到 `domain/entities` 的 Beanie Document。
- 将 `ResourceIndexWriter`、`AppliedStructureReader`、`AppliedContentReader` port 收归 `domain/repositories`。
- 将 revision 身份与 staged 决策改名为 `application/rag/index/revisions.py`。

验收：Beanie 依赖可解析，repository 不反向依赖 application model，既有 revision/store 测试保持通过。

Commit：`rag-v2 cp06.1: align persistence with beanie entities and domain repositories`

### CP07：无状态 READ

范围：

- `AppliedStructureReader`、`AppliedContentReader`。
- `get_document_structure`。
- `get_pages`。
- `get_sections`。
- Section frontier 和 ReadingBlock 顺序。

验收：存在、部分缺失、合法空 Section、重复 page label、page overlap 和 applied-only 测试。

排除：navigation state、ACL、HTTP schema 和 Agent reason。

Commit：`rag-v2 cp07: implement deterministic content reads`

### CP08：VERIFY 回源

范围：

- EvidenceReader。
- SourceRef 原文拼接和 content hash 校验。
- candidate chunk/block/ref/revision 归属校验。
- 缺 part、span 越界和 revision 不一致异常。

验收：精确 evidence、跨 part、缺失 ref、错误 block、内容损坏测试。

排除：ACL 最终复查、LOCATE 和图关系。

Commit：`rag-v2 cp08: verify evidence against applied source`

### CP09：ACL 领域规则

范围：

- `PermissionScope`、`ResourceAcl` 和 `GroupResourceAcl` 的最小事实。
- owner、直接用户、资源排除、managed group、joined group 规则。
- 单资源 authorize 与批量 readable resource 计算。
- Qdrant/Neo4j 使用的统一权限表达输入。
- `PermissionAuthorizer` 面向对象用例，以及 `read` 的结构/正文读取对象。
- 使用 dependency-injector 装配 READ 的 Mongo port 和 ACL reader dependency。

验收：完整 ACL 真值表，资源排除优先级和本地 ACL 缺失 fail-closed 测试。

排除：ACL Mongo、Qdrant、Neo4j 和安全上下文 adapter；READ 不新增业务能力，只完成对象化装配。

Commit：`rag-v2 cp09: define resource authorization rules`

### CP10：ACL Mongo 边界

范围：

- AuthoritativeAclReader，只读上游 `wisepen_resource_items`。
- ResourceAclStore，本地 `resource_acls`。
- acl revision 幂等 upsert 与资源删除。
- 权威读取与本地读取使用两个明确 adapter。

验收：上游缺失、本地缺失、旧 revision、不合法 ObjectId/上游数据和批量读取测试。

排除：Kafka 事件和 Qdrant/Neo4j ACL 同步。

Commit：`rag-v2 cp10: separate authoritative and local ACL stores`

### CP11：模型生成缓存

范围：

- `generation_cache` collection。
- `contextual_text` 与 `graph_candidates` 两个 cache kind。
- resource-local get/set/delete。
- prompt/schema/model/input cache key 规则。

验收：批量部分命中、kind 隔离、resource 隔离、覆盖和删除测试。

排除：真实 LLM 调用和 index orchestration。

Commit：`rag-v2 cp11: add resource-scoped generation cache`

### CP12：Contextual indexing

范围：

- RetrievalChunk contextual text 生成。
- 模型调用协议和严格响应解析。
- generation cache 复用。
- 只增强 `index_text`，不改 raw text/span/SourceRef。

验收：cache hit/miss、并发、空响应、模型错误和原文不变测试。

排除：embedding、Qdrant 和图抽取。

Commit：`rag-v2 cp12: generate contextual retrieval text`

### CP13：Qdrant 写入

范围：

- v2 collection schema、dense/BM25 vectors 和必要 payload index。
- RetrievalIndexWriter。
- embedding key 与 dense vector 复用。
- `active=false` stage、revision 激活、旧 revision 清理和资源删除。

验收：collection 初始化、payload 契约、向量维度、stage/activate/retry/delete 测试。

排除：CandidateSearch、query embedding 和 rerank。

Commit：`rag-v2 cp13: write revisioned retrieval index`

### CP14：Qdrant 候选召回

范围：

- CandidateSearch。
- dense/BM25 查询与融合。
- active/resource/ACL filter。
- 最小 candidate payload 映射。

验收：语义与词法 query 分工、resource filter、ACL filter、inactive revision 和缺失 payload 测试。

排除：application rerank、ReadingBlock 去重和 state 创建。

Commit：`rag-v2 cp14: search active retrieval candidates`

### CP15：Redis Navigation state

范围：

- 单 hash key state schema。
- create/load/add sections/add nodes。
- user/session/root query、Section resource/revision 身份和统一 TTL。
- Lua 或等价原子 exists-and-add。

验收：并发追加、过期、缺失 state、TTL 续期、Section revision 值测试。

排除：LOCATE/READ/EXPAND 用例。

Commit：`rag-v2 cp15: persist atomic navigation state`

### CP16：LOCATE 主链

范围：

- semantic query embedding 与 lexical fallback。
- CandidateSearch 调用和 application rerank。
- relevant/uncertain/irrelevant 判定。
- `(resource_id, reading_block_id)` 去重。
- ACL 最终过滤、VERIFY 回源、Section 入口和 navigation state 创建。

验收：单次 embedding、rerank 输入、阈值、同 Section 多 block、ACL 变化和 state 创建测试。

排除：知识节点解析、HTTP endpoint 和 MCP payload。

Commit：`rag-v2 cp16: locate verified reading entries`

### CP17：图抽取窗口与候选校验

范围：

- ReadingBlock 级 extraction window。
- 父上下文、相邻 block 边界和 SourceRef 映射。
- GraphRAG SDK adapter。
- 节点、关系、assertion、evidence quote 的候选校验。
- graph candidate cache。

验收：窗口边界、连续 quote、非法 node/relation、非 affirmed 和 cache 重校验测试。

排除：节点合并和 Neo4j。

Commit：`rag-v2 cp17: extract and validate graph candidates`

### CP18：知识图谱合并

范围：

- 节点 label canonicalization 和稳定 ID。
- 等价节点合并。
- relation 聚合、predicate 和 evidence 去重。
- MENTIONS 构建。
- graph revision 计算。

验收：Unicode/NFKC、大小写、重复 evidence、多窗口等价关系和稳定 revision 测试。

排除：Neo4j query、图发布状态和 EXPAND。

Commit：`rag-v2 cp18: merge canonical knowledge graph`

### CP19：Neo4j 图写入

范围：

- v2 graph namespace、constraint 和 index。
- KnowledgeGraphWriter。
- building/published/skipped 状态机。
- node/relation/mention 写入、并发 CAS、旧图和孤立节点清理。

验收：publish、skip、superseded revision、重复写入、sectioned/flat/empty 转换和删除测试。

排除：MentionLookup、GraphTraversal 和 ACL 同步。

Commit：`rag-v2 cp19: publish revisioned knowledge graph`

### CP20：MentionLookup 与 LOCATE 节点入口

范围：

- MentionLookup。
- 当前 published graph/revision/ACL 过滤。
- LOCATE 使用已核验 SourceRef 解析初始节点。
- 初始 known nodes 写入 state。

验收：无图、skipped 图、旧 revision、无权限、重复 mention 和 limit 测试。

排除：任意路径遍历。

Commit：`rag-v2 cp20: discover graph nodes from located evidence`

### CP21：EXPAND 图遍历

范围：

- GraphTraversal。
- node/relation/direction/depth/limit 过滤。
- published graph 与 evidence ACL 过滤。
- 路径排序、去除无新节点路径、VERIFY 回源和 known nodes 原子扩展。

验收：方向/深度、未知 seed、循环路径、旧图、证据权限、无新节点和并发 state 测试。

排除：HTTP endpoint 和 Agent 渲染。

Commit：`rag-v2 cp21: expand verified graph paths`

### CP22：有状态 READ

范围：

- state user/session 校验。
- 只读取 known sections。
- AppliedContentReader 读取完整正文与 frontier。
- ACL/revision 最终检查。
- 新 Section 原子加入 state。

验收：未知 Section、跨用户、跨 session、revision 变化、ACL 撤销和并发扩展测试。

排除：无状态读取改动和 HTTP endpoint。

Commit：`rag-v2 cp22: read discovered sections through navigation state`

### CP23：ACL 后端同步

范围：

- RetrievalAclWriter。
- GraphAclWriter 和 ResourceGroupAcl。
- ACL refresh application 用例：权威读取、本地 upsert、两个后端显式同步。
- 旧 acl revision 不覆盖新 revision。

验收：Qdrant/Neo4j payload/predicate、部分后端失败重试和全链路 ACL 真值表。

排除：Kafka payload adapter。

Commit：`rag-v2 cp23: synchronize ACL to retrieval and graph stores`

### CP24：文档索引编排

范围：

- 完整 `index_resource` 用例。
- 结构构建、contextual text、embedding、Mongo stage、Qdrant stage、Mongo apply、Qdrant activate、图 publish/skip。
- 重试补偿和 stale event 收敛。

验收：每个步骤单独失败后的事件重试，以及 sectioned/flat/empty 全链路测试。

排除：Kafka schema、删除和 HTTP。

Commit：`rag-v2 cp24: orchestrate resource indexing lifecycle`

### CP25：资源删除编排

范围：

- 显式 fail-closed 删除顺序。
- Mongo state/content/cache、Qdrant、Neo4j、本地 ACL 清理。
- TaskGroup 后端清理与异常直接抛出。
- 重复删除幂等。

验收：每个后端单独失败、重试、state 已缺失和旧 Redis state 不可读测试。

排除：Kafka payload adapter。

Commit：`rag-v2 cp25: delete all resource-derived state`

### CP26：HTTP READ adapter

范围：

- document structure、page content、section content schema 和 endpoints。
- 登录身份与 SecurityContext 到 PermissionScope。
- application 异常到资源读取错误码。
- 批量返回实际存在 key，不生成 Agent reason。

验收：schema 上限、extra forbid、无权限与不存在不可区分、空 Section 和响应契约测试。

排除：navigation endpoints 和 MCP 修改。

Commit：`rag-v2 cp26: expose deterministic read endpoints`

### CP27：HTTP Navigation adapter

范围：

- locate、read discovered sections、expand endpoints。
- navigation state 相关错误码。
- node/edge/path/source 的序列化。
- 请求数量、方向和深度约束。

验收：HTTP contract fixtures、身份不可伪造、state 不存在/失效和依赖失败映射测试。

排除：MCP/Agent reason 组装。

Commit：`rag-v2 cp27: expose knowledge navigation endpoints`

### CP28：Kafka adapters 与服务装配

范围：

- document ready、ACL recalc、resource destroy payload schemas。
- retry/offset 所需异常分类。
- dependency container、配置、schema initialize、health 和 lifecycle。
- 三类 consumer 接入 CP23/CP24/CP25 用例。

验收：非法 payload、handler 抛错、启动/关闭、配置缺失、health 和 import side-effect 测试。

排除：调用方切流和 v1 数据删除。

Commit：`rag-v2 cp28: wire service adapters and lifecycle`

### CP29：集成门与影子对照

范围：

- v1/v2 document、READ、LOCATE、EXPAND、VERIFY golden fixtures。
- ACL 真值表跨 Mongo/Qdrant/Neo4j/最终回源。
- revision 并发、故障恢复和资源删除集成测试。
- shadow read 对比脚本与差异报告格式。
- 回放和切流 runbook。

验收：全量 v2 tests、compileall、lint、diff check 全部通过，所有行为差异有明确批准记录。

排除：实际生产切流、停止 v1 consumer 和删除 v1 数据。

Commit：`rag-v2 cp29: validate parity and cutover readiness`

## 4. 跨边界改动处理

某个 checkpoint 如果发现必须修改另一个能力：

1. 停止当前实现，不在同一 commit 顺手修改。
2. 判断缺口是架构遗漏、port 契约缺失还是实现顺序错误。
3. 架构变化先单独提交文档 checkpoint。
4. port 变化先在 owner checkpoint 提交，再在后续 consumer checkpoint 使用。
5. 不使用临时兼容类、转发 helper 或重复 model 跨过顺序约束。

只有纯机械的同名引用更新可以与 owner 实现同提交；一旦包含新的业务判断、字段、异常或存储副作用，就必须拆 checkpoint。

## 5. Checkpoint 记录模板

每次提交完成后，在工作记录中保留：

```text
Checkpoint: CPxx
Commit: <hash>
Scope: <本次唯一职责>
Files: <变更路径>
Tests: <实际运行命令和结果>
Deferred: <明确留给后续 checkpoint 的事项>
```

不得用“顺便完成”“后续兼容”“相关调整”描述提交范围。无法用一句具体业务动作概括的 commit 必须继续拆分。
