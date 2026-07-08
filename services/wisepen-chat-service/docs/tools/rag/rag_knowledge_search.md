# rag_knowledge_search

## 实现入口

| 层 | 文件 |
| --- | --- |
| 工具门面 | `src/chat/application/tools/rag_tools/knowledge_search_tool.py` |
| 应用服务 | `src/chat/application/rag/knowledge_search.py` |
| 检索编排 | `src/chat/application/rag/retrieval/retrieval_pipeline.py` |
| Ranking 节点 | `src/chat/application/rag/retrieval/pipeline/ranking.py` |
| 注册入口 | `src/chat/container.py` |

## 何时使用

- 用户要从已附加、已选中或当前上下文明确给出的 WisePen 私有知识资源中回答问题。
- 当前轮已知 `resource_id`。
- 需要主模型显式选择 `balanced`、`semantic` 或 `lexical` 检索模式。

## 何时禁止使用

- 不知道目标 `resource_id`。
- 用户要实时互联网信息，应使用 `web_search` / `web_fetch`。
- 用户要读取已有 `cnt_*` 内容，应使用 `tool_content_rerank_read`、`tool_content_regex_read` 或 `tool_content_sequential_read`。
- 不得让模型传入用户 ID、群组角色、ACL projection、Qdrant point id、Neo4j node id 或 chunk 内部 ID。

## 参数契约

schema 负责校验：

- `query`、`resource_id` 必填且非空。
- `retrieval_profile` 只能是 `balanced`、`semantic`、`lexical`。
- `keywords` 是可选精确内容短语，只用于 Elastic chunk 内容关键词过滤。

`top_k`、`candidate_limit`、`elastic_prefilter_limit` 是运维调参项，只能从 `app_settings` 读取，不允许模型参数注入。版本字段只作为系统内部版本标识存在，不进入模型入参。

安全上下文来自 `context`：

- `user_id`
- `session_id`

当前第一版工具用 `user_id + 空 group_role_map` 构造 `RagPermissionScope`，覆盖 owner/readable_users 权限路径。后续如果聊天上下文提供可信 group role map，再扩展该 context，不允许模型参数传入。

## 内部机制

```text
rag_knowledge_search
  -> RagKnowledgeSearcher.search
  -> RagRetrievalPipeline
     -> RagElasticFilter.filter_candidate_chunk_ids
     -> RagQdrantRetriever.retrieve
     -> RagEvidenceRankingService
     -> RagGraphEnhancement.enhance
  -> AnswerabilityHardGate / AnswerabilitySoftGate
  -> RagEvidenceMaterializer
  -> RagContextBuilder
```

工具只做薄门面：参数归一、可信权限 scope 注入、调用应用服务、构造模型可见返回。

## 主链路边界

RAG 主链路采用 `Elastic keyword prefilter -> Qdrant dense + BM25 -> RankingEngine -> direct_evidence`。

几个边界必须保持稳定：

- Qdrant 是主召回源，同时承担 dense vector 和 BM25 sparse 检索。
- Elastic 只做 chunk `indexing_text` 的严格关键词前置过滤，不作为一路召回源，不参与最终 topK 融合。
- Elastic 只在 `keywords` 非空时启用，返回 candidate chunk id scope；没有关键词时直接跳过。
- Qdrant filter 只表达资源范围、Elastic candidate scope 和 ACL 权限范围，不做内容过滤或版本过滤。
- RankingEngine 是 retrieval pipeline 内部阶段，只处理主召回候选，负责最终 direct evidence 的融合、重排、过滤和多样化；下游只消费已排序候选。
- Neo4j graph enhancement 不混入主 topK，只输出 `graph_evidence` 和 `ontology_hints`。

版本字段是系统内部版本化标识，只用于入库、回源、缓存签名和引用定位；模型不得注入任何 version 字段，也不得把 version 当作事实源或排序信号。

## Answerability 边界

Answerability 分为 Hard Gate 和 Soft Gate。

Hard Gate 是服务端硬拒答，只处理确定失败：

- `EMPTY_RETRIEVAL`：没有可用候选。
- `TOPK_ALL_BELOW_ABSOLUTE_MIN_SCORE`：候选整体低于最低可用阈值。

Hard Gate 拒绝后不进入 Soft Gate、Neo4j enhancement 或主模型知识性回答。

Soft Gate 不拒答，只输出 warning 和 guidance。它用于判断 direct evidence 是否存在低直接性、覆盖不足、证据冲突等风险；一旦需要补充结构化证据，就触发 Neo4j enhancement。主模型最终仍必须基于 citation 和 evidence 边界作答。

## Graph Enhancement 边界

Neo4j 在当前 RAG 中是后置增强层，不是普通召回通道。

Graph 只做这些事：

- 围绕 child chunk 构建 evidence-backed concept graph。
- 基于 direct evidence seed 扩展相关 chunk / concept path。
- 在 Soft Gate warning 后补充 `graph_evidence` 或 `ontology_hints`。
- 帮助实体关联、概念消歧、关系提示和多跳路径解释。

Graph 不做这些事：

- 不替代 Qdrant 主召回。
- 不参与 direct evidence topK 竞争。
- 不绕过 ACL。
- 不把图路径本身当作最终事实源；进入上下文的仍必须是带 citation 的 evidence。

知识图谱构建使用 `neo4j-graphrag` 组件，边界封装在 `src/chat/application/rag/graph/graphrag_builder.py`。SDK 的 Pydantic 输入统一通过 `model_validate` 构造，避免静态分析把 Pydantic 模型字段误判为意外实参。

## 缓存边界

RAG 缓存只优化中间步骤，不缓存最终答案，也不替代权限判断。

当前只保留三类缓存：

- Ingestion Deterministic Cache：缓存分块、context indexing、embedding 等确定性入库中间结果。
- Authorized Evidence Materialization Cache：在同一 user、session、ACL scope 下复用已授权 evidence 的 parent 回源文本和 citation 定位。
- Graph Enhancement Cache：缓存同一资源、同一 direct evidence signature、同一 warning scope、同一 ACL scope 下的 Neo4j enhancement 结果。

缓存准入原则：

- 权限 scope 不确定时 cache miss。
- ACL 变化不能复用权限投影。
- 缓存不能绕过 evidence 回源和权限边界。
- 缓存不围绕 query 字符串，也不缓存 final answer。

## 输出结构

工具返回 `ToolReturn(tag="rag_knowledge_search_result")`。

`visible_result` 包含：

- `answerability.status`
- `answerability.reason`
- `answerability.warnings`
- `answerability.guidance`
- `direct_evidence` 的 `citation_id`、页码、章节、锚点标签、短 excerpt
- `graph_evidence` 的页码、章节、锚点标签、相关概念、短 excerpt
- `ontology_hints`

`visible_result` 不回显 `resource_id`、`retrieval_profile`、检索数量、rank、score、Elastic 预过滤命中状态、parent chunk id 或 child chunk id。

`cacheable_texts` 包含一份去内部 ID、rank 和 score 的 evidence context。文本较短时会内联，较长时由 `ToolOutputCache` 生成 `cnt_*`。

## 模型约束

- direct evidence 只能用 `citation_id` 引用证据；定位信息使用 `page_label`、`section_path`、`anchor_labels`。
- Hard Gate 被拒时不得生成实质答案。
- Soft Gate warning 存在时必须保守回答，并说明证据边界。
- 不得伪造不存在的证据、资源版本或 citation。
- 不得把 visible result 中没有出现的内部检索 ID 当作引用。

## 可插拔点

- Retrieval pipeline：Elastic filter、Qdrant retriever、Graph enhancement。
- Ranking：`rag.knowledge_search` RankingEngine。
- Answerability：Hard Gate / Soft Gate。
- Cache：RAG ingestion deterministic cache、evidence materialization cache、graph enhancement cache。
- Graph builder：`neo4j-graphrag` 适配层。

## 相关测试

- `tests/rag/test_knowledge_search_tool.py`
- `tests/rag/test_retrieval_pipeline.py`
- `tests/api/test_tool_catalog.py`
