# WisePen RAG 实现接手文档

日期：2026-06-27  
状态：RAG 方案已阶段性定稿，当前只完成应用层占位、Context Indexing 小模型调用、RAG ranking engine 注册。  
读者：下一位继续实现 WisePen 私有知识库 RAG 的模型。

## 1. 接手前必须先读

先读规范，再读代码，不要只按本文档继续写。

1. `docs/ai_assist/00-index.md`
2. `docs/team/05-utils-inventory.md`
3. `docs/plans/rag/00-index.md`
4. `docs/plans/rag/03-rag-complete-solution.md`
5. `src/chat/application/rag/`
6. `src/chat/application/utils/chunking_engine/`
7. `src/chat/application/utils/ranking_engine/`
8. `src/chat/application/utils/llm_clients/`
9. `src/chat/service_client/resource_service_client.py`

注意：`03-rag-complete-solution.md` 已同步为当前长期方案口径；本文只补充当前实现状态和接手顺序。

## 2. 当前定稿

### 2.1 总体架构

第一版采用：

```text
长期知识库 Corpus
  -> parent-child chunking
  -> Context Indexing
  -> Qdrant dense retrieval + Elasticsearch lexical retrieval
  -> application-side fusion / upstream score fusion
  -> rag.knowledge_search ranking post-process
  -> Context Builder
  -> prompt 前 resource-service VIEW hard auth
  -> answer with citations

旁路增强：
seed chunks
  -> bounded concept graph expansion
  -> evidence chunks
  -> Context Builder
```

硬边界：

- RAG 是长期业务索引体系，不是 `cnt_*`、`tfile_*`、`web_content_cache` 这类工具缓存体系。
- `resource_id` 是权限根。
- 第一版 RAG 查询准入只使用 `VIEW`，不新增 `QUERY`。
- 预计算 `acl_projection` 是检索前强制准入条件。
- Qdrant、Elasticsearch、Mongo、Graph 检索都必须先带 ACL filter。
- prompt 前还要按 `resource_id` 批量调用 resource-service 做 `VIEW` hard auth。
- Context Builder 是唯一决定什么进入 prompt 的组件。

### 2.2 论文取舍

三篇论文的最终取舍已经收敛：

| 论文 | 最终采纳 |
| --- | --- |
| InSemRAG | 只采纳“主模型意图路由 / retrieval profile”思想。主模型持有完整上下文，由主模型显式选择 `balanced`、`semantic`、`lexical`、`anchored_exact`。服务端只做确定性计划映射和执行。 |
| Grounded Decoding | 第一版不采纳，不做 POC 前置，不影响当前主链。不要实现 token 概率融合、双流 decoding 或近似命名为 Grounded Decoding 的东西。 |
| Predictive Prefetching | 第一版不采纳。不要新增 prefetch coordinator、prefetch cache 或 hidden-state predictor。后续如要降延迟，另起任务评估。 |

这条取舍来自 web search 重构经验：小模型隐式路由、自动改写 query、自动多跳搜索收益低且容易过早收窄搜索面。RAG 也遵守同一原则：

```text
主模型负责显式选择检索模式。
RAG service 负责可审计、可测试、权限安全的确定性执行。
小模型不做隐式路由主控。
```

### 2.3 检索模式

保留四种模型可见 profile：

| profile | 语义 | 服务端执行倾向 |
| --- | --- | --- |
| `balanced` | 默认问答，没有明显锚点 | Qdrant dense + Elasticsearch lexical 均衡。 |
| `semantic` | 概念解释、同义表达、用户描述不精确 | dense 权重更高，Elastic 保留兜底。 |
| `lexical` | 明确术语、标题、配置项、错误片段 | Elasticsearch BM25 / field boost 权重更高，dense 补语义邻近。 |
| `anchored_exact` | 版本号、错误码、函数名、文件名、quoted phrase | `must_terms`、`quoted_phrases`、keyword 字段、必要 hard filter 共同约束。 |

重要判断：

- Elasticsearch/BM25 可以承担 lexical retrieval，但不能单独承担“精确检索”。
- `anchored_exact` 不能只靠 BM25 排名前置，必须有 `must_terms`、`quoted_phrases`、keyword 字段或等价 hard constraint。
- 模型可以选择 profile，但不能直接传任意底层权重。

### 2.4 Context Indexing

当前定稿是：Context Indexing 必须调用小模型，不做 deterministic fallback。

原因：

- `context_summary`、`important_terms` 不是稳定的规则提取结果。
- `parent_summary`、`previous_summary`、`next_summary` 这类上下文也不能靠规则可靠生成。
- 如果小模型失败，宁愿入库任务失败并后续重试，也不要写入质量参差的 fallback 文本污染长期知识库。

当前输入必须带：

```text
parent_text
child_text
document_title
section_path
```

`parent_text` 是 child 所在父块全文，用来判断 child 的局部语义位置和术语边界。输出中：

- `evidence_text` 保留未改写的 child 原文，用于最终引用。
- `indexing_text` 用于 embedding、Elasticsearch lexical index、图抽取消歧。
- `used_llm` 字段已删除，因为 LLM 是硬约束，不是可选能力。

## 3. 当前已实现代码

### 3.1 RAG 应用层目录

已新增占位：

```text
src/chat/application/rag/
  __init__.py
  models.py
  ingestion/
  retrieval/
  permission/
  graph/
  context_builder/
  evaluation/
```

这些目录只是应用层业务子系统占位。不要把 RAG 主逻辑塞进 `tools/`。如果后续要暴露模型工具，再新增薄门面：

```text
src/chat/application/tools/rag_tools/
  knowledge_search_tool.py
  knowledge_graph_explore_tool.py
```

工具门面只负责 schema、preflight、service 调度和错误包装，不直接查 Qdrant/Mongo/Elastic。

### 3.2 Context Indexing

当前实现：

- `src/chat/application/rag/ingestion/models.py`
- `src/chat/application/rag/ingestion/context_indexing.py`
- `tests/rag/test_context_indexing.py`

稳定行为：

- `ContextIndexingInput(parent_text, child_text, document_title="", section_path=())`
- `ContextIndexingService.build(payload)`
- 使用 `LiteLLMQueryClient.aquery()` 和 `settings.SUMMARY_MODEL`
- `temperature=0.0`
- `max_tokens=256`
- LLM 返回必须是严格 JSON：

```json
{
  "context_summary": "这个片段在文档中的局部语义作用",
  "important_terms": ["术语1", "术语2"]
}
```

失败策略：

- JSON 非法、字段类型错误、LLM 调用异常，都抛 `ContextIndexingError`
- 调用方应把入库任务标记为可重试
- 不允许 fallback 写入低质量 `indexing_text`

已经验证：

```text
python -m py_compile services/wisepen-chat-service/src/chat/application/rag/ingestion/models.py services/wisepen-chat-service/src/chat/application/rag/ingestion/context_indexing.py
python -m pytest services/wisepen-chat-service/tests/rag/test_context_indexing.py -q
```

结果：`3 passed`。

### 3.3 RAG ranking engine

已在 `src/chat/application/utils/ranking_engine/registry.py` 注册：

```text
rag.knowledge_search
```

当前职责是 post-process，不做上游检索分数计算：

- Qdrant 和 Elasticsearch 已经各自完成打分。
- 上游 RAG orchestrator 负责 score normalization / fusion 或按 fused order 传入候选。
- `rag.knowledge_search` 从输入顺序起步，只做 `ZeroEntropyReranker` 和 MMR 多样性控制。

当前配置：

```text
reranker = get_default_zero_entropy_reranker()
diversifier = MmrDiversifier(
  tokenizer = ThuLacRankingTokenizer(),
  lambda_mult = 0.78,
  same_group_similarity = 0.95,
)
```

不要在这个 engine 里重新接 BM25 计算 Qdrant/Elastic 已经打过的分。若后续 orchestrator 传入多路候选且尚未融合，应在 RAG retrieval 层完成融合，再交给 ranking engine 做最终 rerank/MMR。

### 3.4 可复用工具函数和组件

优先复用这些能力：

| 需求 | 入口 |
| --- | --- |
| 父子块切分 | `get_chunking_pipeline("nested_markdown")`，定义在 `src/chat/application/utils/chunking_engine/registry.py` |
| 分块执行 | `ChunkingEngine`、`ChunkDocument` |
| 分块索引 | `ChunkExtraIndexer` 产生 section/page/anchor indexes |
| 小模型调用 | `build_query_client()`、`LiteLLMQueryClient` |
| embedding | `build_embedding_client()`、`LiteLLMEmbeddingClient` |
| 排序后处理 | `get_ranking_engine("rag.knowledge_search")` |
| 权限事实源 | `ResourceClient.check_res_permission()` |
| 当前用户上下文 | `SecurityContextHolder.get_user_id()`、`SecurityContextHolder.get_group_role_map()` |

权限调用示例参考：

```text
src/chat/application/tools/skill_tools/common/checks.py
```

`ResourceClient` 定义在：

```text
src/chat/service_client/resource_service_client.py
```

## 4. 不要做的事

这些是已经讨论过并排除的路线：

- 不要恢复 web search 式小模型隐式路由。
- 不要让小模型自动改写 RAG query、自动多跳 retry 作为主控。
- 不要实现 Grounded Decoding 或把普通 verifier 命名成 Grounded Decoding。
- 不要实现 Predictive Prefetching，也不要提前加 prefetch cache。
- 不要把完整图谱默认塞进 prompt。
- 不要让模型自由传 graph node id 做全图探索。
- 不要把 BM25 叫成“精确检索”的唯一实现。
- 不要把 `cnt_*`、`tfile_*`、URL cache ID 当长期 KB ID。
- 不要无 ACL filter 召回 topK 再逐条过滤。
- 不要让 Qdrant filter 替代 prompt 前 resource-service hard auth。
- 不要把 ACL projection、Qdrant point id、Mongo `_id` 暴露给模型。
- 不要在 Context Indexing 失败时写 deterministic fallback。

## 5. 推荐下一步实现顺序

### Step 1：补 RAG 数据模型和状态枚举

建议先落应用层 DTO，再落 domain/entity/repository。

优先模型：

```text
RagRetrievalProfile = balanced | semantic | lexical | anchored_exact
RagRetrievalRequest
RagRetrievalPlan
RagCandidate
RagContextItem
AclProjection
```

如果固定取值较多，用 `StrEnum`，不要散落裸字符串。

### Step 2：实现 RetrievalPlanBuilder

位置建议：

```text
src/chat/application/rag/retrieval/
  models.py
  retrieval_plan_builder.py
```

职责：

- 接收主模型选择的 profile 和 anchors。
- 映射成服务端固定检索计划。
- 拒绝模型传任意底层权重。
- 明确 Qdrant topK、Elastic topK、fusion 策略、required hard constraints。

第一版只做确定性 mapping，不调用小模型。

### Step 3：实现权限投影 DTO 和 filter builder

位置建议：

```text
src/chat/application/rag/permission/
  models.py
  acl_filter_builder.py
  rag_permission_checker.py
```

职责：

- 表达 `AclProjection`。
- 从 `user_id + group_role_map` 构造 Qdrant/Elastic/Mongo 等价 ACL filter。
- 封装 prompt 前 hard auth。

注意：

- resource-service 是权限事实源。
- projection 只是检索准入投影。
- `projection_status != active` 默认不可检索。

### Step 4：接 parent-child ingestion

基于：

```text
get_chunking_pipeline("nested_markdown")
ContextIndexingService
LiteLLMEmbeddingClient
```

建议流程：

```text
normalized Markdown
  -> nested_markdown pipeline
  -> parent chunks / child chunks
  -> for each child: ContextIndexingService.build(parent_text, child_text)
  -> embedding(indexing_text)
  -> Mongo child record
  -> Qdrant point
  -> Elasticsearch doc
```

第一版 Graph extraction 可以继续占位，不阻塞主检索。

### Step 5：实现 hybrid retrieval orchestrator

位置建议：

```text
src/chat/application/rag/retrieval/
  hybrid_retrieval_orchestrator.py
```

职责：

- 根据 RetrievalPlan 并行查 Qdrant 和 Elasticsearch。
- 两边都必须带 ACL filter。
- 对结果做 fusion 或接受上游 score 后合并。
- hydrate Mongo chunk/parent。
- 丢弃 deleted/stale/version mismatch/projection inactive 候选。
- 调用 `get_ranking_engine("rag.knowledge_search")` 做最终 rerank/MMR。

不要把业务检索规则塞进 `ranking_engine`。

### Step 6：Context Builder

位置建议：

```text
src/chat/application/rag/context_builder/
  context_builder.py
  models.py
```

职责：

- 合并 child/parent。
- 控制 token budget。
- 构造 citation map。
- prompt 前按 `resource_id` 批量 hard auth。
- 返回模型可见 evidence，不返回内部存储 ID。

### Step 7：最后再做工具门面

等 application service 稳定后再新增：

```text
src/chat/application/tools/rag_tools/knowledge_search_tool.py
```

工具返回原则：

- 小 evidence 直接普通结构化返回。
- 长 evidence 才走 `ToolReturn.cacheable_texts` 生成本轮 `cnt_*`。
- visible result 只放 citation、标题、章节、页码、短 excerpt、warnings。
- 不暴露长期内部 ID、ACL projection、Qdrant point id。

## 6. 文档同步状态

已同步：

- `03-rag-complete-solution.md` 已改为 LLM-required Context Indexing，失败可重试，不 fallback。
- 论文深读稿已从计划索引移除；当前长期方案不再保留论文精读材料。
- `05-rag-final-solution-deck.html` 已同步为当前定稿展示口径。

本文是短期接手文档，不替代长期 team 文档。等 RAG 第一版代码稳定后，应把稳定规则迁移到 `docs/team/` 或 `docs/tools/rag/`。

## 7. 当前验收状态

已完成：

- RAG 应用层目录占位。
- `ContextIndexingService` 小模型调用。
- Context Indexing 不再支持 fallback。
- Context Indexing 输入要求 `parent_text` 和 `child_text`。
- 删除 `used_llm`。
- 注册 `rag.knowledge_search` ranking engine。
- `tests/rag/test_context_indexing.py` 通过。

未完成：

- RAG domain entities。
- Mongo repositories。
- Qdrant repository。
- Elasticsearch repository。
- ACL projection builder。
- RetrievalPlanBuilder。
- hybrid retrieval orchestrator。
- Context Builder。
- `knowledge_search` tool。
- concept graph extraction / exploration。
- eval dataset。

下一位模型请从 Step 1 或 Step 2 开始，不要跳到工具门面。
