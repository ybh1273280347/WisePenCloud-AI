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
| 当前 CP08 | 未提交 | VERIFY 回源闭环和本交接文档，待本会话提交为 `rag-v2 cp08: verify evidence against applied source`。 |

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

- Mongo Document 必须放在 `domain/entities`，当前为 `content_index.py` 中的 Beanie entities。
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

最近一次验证结果：

```text
uv run pytest -q                                  -> 34 passed
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

当前没有真实 Mongo/Beanie 集成测试；下一阶段接手时应先决定是否补一个使用测试 Mongo 的 adapter 集成测试，再接入 orchestration。

## 6. 当前待提交文件

本次 CP08 尚未提交，工作树中预期包含：

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

下一个稳定 checkpoint 是 CP09：ACL 领域规则。

CP09 只做：

- `PermissionScope`、`ResourceAcl` 等最小权限事实。
- owner、直接用户、资源排除、managed group、joined group 规则。
- 单资源 authorize 和批量 readable resource 计算。
- Qdrant/Neo4j 可消费的统一权限表达输入。
- 完整 ACL 真值表和 fail-closed 测试。

CP09 不得做：

- Mongo ACL adapter。
- Qdrant/Neo4j ACL 同步。
- HTTP、Kafka、Agent 业务语义。
- 修改 VERIFY 的证据校验。

后续顺序仍以 `Migration.md` 为准：CP10 ACL Mongo，CP11 generation cache，CP12 contextual indexing，CP13-14 Qdrant，CP15 Redis state，CP16 LOCATE，CP17-19 图谱，CP20-25 导航/编排/删除，CP26-28 adapters，CP29 集成门。

## 8. 接手禁区

1. 不要恢复 `snapshot`、`projection`、`ResourceSnapshotRepository` 等旧抽象。
2. 不要建立全局 `models.py`、`common.py` 或错误 reason/status 传递层。
3. 不要为了测试重新增加第二种 adapter 构造方式。
4. 不要把 Agent 探索语义塞回 RAG。
5. 不要把 Qdrant payload 或 Neo4j record 当权威正文。
6. 不要在一个 checkpoint 顺手跨越多个 application 能力。
