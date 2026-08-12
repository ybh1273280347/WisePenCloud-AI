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
| 当前 CP14 | 待提交 | Qdrant dense/BM25 混合候选召回、active/resource/ACL 过滤和最小候选映射。 |

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

`verify_candidates()` 会校验：

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

最近一次已提交 checkpoint 的验证结果：

```text
uv run pytest -q                                  -> 50 passed
uv run ruff check <CP08 新增/修改文件>              -> All checks passed
uv run python -m compileall -q src tests           -> passed
```

测试覆盖：

- index revision identity 和 stage decision。
- READ 缺失 applied revision 直接失败。
- VERIFY 正常回源。
- 缺失 SourceRef。
- chunk 与 SourceRef 身份不一致。
- revision 不一致。

CP14 最近一次工作树验证：

```text
uv run pytest                                      -> 待全量验证
uv run python -m compileall -q src/rag             -> passed
uv run ruff check <CP13 target paths>              -> passed
```

CP10 新增了上游 ACL 字段映射、无效资源 ID、缺失资源和容器装配测试；CP11 新增 generation cache 的批量命中、类别/资源隔离、覆盖和删除测试；CP12 新增 contextual text 的 cache hit/miss、严格响应、跳过和原文不变测试；CP13 新增 Qdrant collection、payload、向量复用、revision 激活/清理和错误归属测试；CP14 新增 dense/BM25 融合、active/resource/ACL filter、候选 payload 校验和空集合测试；当前仍没有真实 Mongo/Beanie/Qdrant 集成测试。

## 6. 当前工作树状态

CP08 已提交为 `81a47997e`，CP08.1 已提交为 `79c350634`，CP08.2 已提交为 `634c4d24f`，CP08.3 已提交为 `9d0a1bc46`，CP08.4 已提交为 `a8eeaaef6`，CP09 已提交为 `b16b7d630`，CP10 已提交为 `06d46fb3d`，CP10.1 已提交为 `fb931795e`，CP11 已提交为 `df411431c`，CP12 已提交为 `c5113eb44`，CP13 已提交为 `21ac955f8`。当前 CP14 正在完成 Qdrant CandidateSearch；提交后后续会话应从该新 checkpoint 的干净工作树开始，不要改写已有提交。

CP08.1 的稳定边界：

- `ResourceIndexWriter` 只负责 stage、apply、delete；CAS 所需状态读取留在 adapter 内部。
- `AppliedStructureReader` 只获取 applied document structure。
- `AppliedContentReader` 只获取 page/Section 正文和 frontier。
- `GraphBuildSourceReader` 只为 index 图构建阶段读取指定 revision 的输入。
- `index/structure.py` 构建结构事实，`read/structure.py` 获取已发布结构。
- READ application 动作统一为 `get_document_structure`、`get_pages`、`get_sections`。

CP08.2 的稳定边界：

- `core/persistence/mongo/mappers/serializer.py` 只负责领域事实到 Mongo 字段的序列化。
- `core/persistence/mongo/mappers/deserializer.py` 负责 Mongo Entity 或上游记录到领域事实的反序列化，并在不满足外部数据契约时直接抛出异常。
- 内容和 ACL 映射统一使用这两个文件；仓储 adapter 不再私有复制 `*_document` 或 `to_*` 映射函数。
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

当前 checkpoint 是 CP13：Qdrant retrieval index 写入。

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

后续顺序仍以 `Migration.md` 为准：CP12 contextual indexing，CP13-14 Qdrant，CP15 Redis state，CP16 LOCATE，CP17-19 图谱，CP20-25 导航/编排/删除，CP26-28 adapters，CP29 集成门。

CP13 的实现边界：

- `RetrievalIndexWriter` 位于 `domain/repositories`，只接收 `RetrievalChunk`、`SourceRef`、`ResourceAcl` 和 dense vector，不暴露 Qdrant 原生类型。
- `QdrantRetrievalIndexWriter` 位于 `core/persistence/qdrant`，负责 collection 创建、payload index、dense vector 复用、staged point 写入、revision 激活、旧 revision 清理和资源删除。
- Qdrant payload 的领域到存储字段映射集中在 `core/persistence/qdrant/mappers/serializer.py`；CP13 没有候选读取，因此不新增反序列化器。
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

## 8. 接手禁区

1. 不要恢复 `snapshot`、`projection`、`ResourceSnapshotRepository` 等旧抽象。
2. 不要建立全局 `models.py`、`common.py` 或错误 reason/status 传递层。
3. 不要为了测试重新增加第二种 adapter 构造方式。
4. 不要把 Agent 探索语义塞回 RAG。
5. 不要把 Qdrant payload 或 Neo4j record 当权威正文。
6. 不要在一个 checkpoint 顺手跨越多个 application 能力。
