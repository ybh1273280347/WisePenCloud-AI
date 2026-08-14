# RAG v2 review guide

这份文档是给人类 reviewer 看的：按 `locate / read / verify / expand / index` 五个模块看能力，不看实现细节花活。

## 1. locate：先找“可以继续读”的入口

目标：从问题里召回 RetrievalChunk，核验后提升成完整 ReadingBlock，并返回可继续确定性阅读的 section 锚点和 graph 节点。

流程：
1. 接口接收 `semantic_query`、可选 `lexical_query`、资源白名单和 `max_results`。
2. `ReadingCandidateLocator` 先做召回，再做排序。
3. 按 ReadingBlock 去重后做回源校验，并把命中范围换算成 block 内相对字符范围。
4. 将命中的 RetrievalChunk 提升成完整 ReadingBlock，再按 Section 分组。
5. 返回 `state_id`、`retrieval_status`、紧凑 graph nodes 和带 `section_id/title/section_path` 的 section 入口。

对应文件：
- `src/rag/api/endpoints/locate.py`
- `src/rag/api/schemas/locate.py`
- `src/rag/application/rag/navigate/candidate_locator.py`
- `src/rag/application/rag/navigate/__init__.py`
- `src/rag/domain/repositories/qdrant/candidate_searcher.py`
- `src/rag/domain/repositories/neo4j/mention_lookup.py`
- `src/rag/application/rag/navigate/evidence_verifier.py`
- `src/rag/domain/repositories/mongo/readers/applied_structure.py`
- `src/rag/domain/repositories/redis/navigation_state_store.py`

### reviewer 重点
- 命中的 RetrievalChunk 有没有提升成完整 ReadingBlock，而不是泄漏内部候选结构。
- Section 是否同时保留 `section_id`、当前 `title` 和 `section_path`，方便模型定位并继续 READ。
- `level`、revision、重复 source text 等内部或冗余字段有没有泄漏到视图。
- 排序和核验是不是在正确边界内完成。

## 2. read：直接读文档结构、页、section 正文

目标：不经过图谱，不经过检索，直接回答“这个资源长什么样、某一页/某一 section 里有什么”。

流程：
1. `getDocumentStructure` 先拿 applied revision。
2. 结构只返回页面和 section 树，不读正文。
3. `getPageContent` 按页读正文窗口。
4. `getSectionContent` 按 section 直接读直属正文和 frontier，不经过 ReadingBlock。
5. 权限不通过或 applied revision 不存在时直接失败关闭。

对应文件：
- `src/rag/api/endpoints/read.py`
- `src/rag/api/schemas/read.py`
- `src/rag/application/rag/read/structure.py`
- `src/rag/application/rag/read/content.py`
- `src/rag/domain/repositories/mongo/readers/applied_structure.py`
- `src/rag/domain/repositories/mongo/readers/applied_content.py`

### reviewer 重点
- `structure` 读的是结构，不是正文。
- `page` 和 `section` 是两条独立读取路径。
- 所有模型可见页归属统一使用 `page_range`；内部 `page_labels` 只用于请求、索引和回源校验，无页标记时不伪造范围。
- page 的 Section 锚点不带 preview，避免与页正文重复。
- outline 同时保留当前 `title` 和完整 `section_path`；flat text 使用 synthetic Section，确保纯文本也能通过 Section READ 导航和读取。
- outline 去掉无消费价值的 `level`。
- `SectionContent` 是否仍带 frontier，方便继续展开。

## 3. verify：把证据变成可相信的证据

目标：确认候选块、SourceRef、正文、section、page、span 都属于当前 applied revision。

流程：
1. `EvidenceVerifier` 接收候选证据或 graph 引用。
2. 先按 resource 和 revision 分组。
3. 回源读取权威正文。
4. 校验 source_ref、chunk、section、span、page、anchor、raw_text 是否一致。
5. 图关系的引用还要检查 quote 是否真的出现在权威原文里。

对应文件：
- `src/rag/application/rag/navigate/evidence_verifier.py`
- `src/rag/application/rag/navigate/__init__.py`
- `src/rag/core/persistence/mongo/readers/evidence.py`
- `src/rag/domain/repositories/mongo/readers/evidence.py`

### reviewer 重点
- 这里是“核验”，不是“排序”。
- 不要把业务语义 reason 塞进 verifier 里。
- graph 引用和 locate 候选都要能在这里闭环。

## 4. expand：沿已发现图谱节点继续探索

目标：把 navigation state 中已经发现的 graph node 继续展开，并将图证据提升为与 LOCATE 对齐的可读 Section/ReadingBlock 入口。

流程：
1. `expandGraph` 从已知 node 出发找路径、排序、核验证据。
2. application 将路径投影为带有向箭头的可读文本，node ID 只保留作后续导航锚点。
3. 每条关系的 quote 与实际 SourceRef 配对，evidence 按 Section 分组，并回补成与 LOCATE 相同的完整 ReadingBlock 视图。
4. graph 扩展只把新 node 写回 navigation state。
5. 调用方使用证据 Section 的 `section_id` 调用 `getSectionContent`，继续确定性阅读正文与标题导航；新发现节点的 `node_id` 可继续作为 EXPAND seed。

对应文件：
- `src/rag/api/endpoints/expand.py`
- `src/rag/api/schemas/expand.py`
- `src/rag/application/rag/navigate/graph_expander.py`
- `src/rag/application/rag/navigate/__init__.py`
- `src/rag/domain/models/content.py`
- `src/rag/domain/repositories/redis/navigation_state_store.py`
- `src/rag/domain/repositories/neo4j/graph_traversal.py`

### reviewer 重点
- `getSectionContent` 是无状态正文读取能力，任何合法 Section 锚点都可以直接进入。
- ReadingBlock 只属于检索和图证据视图，不能进入确定性 READ 输出。
- `expandGraph` 不能只吐证据片段，必须返回证据所属的完整 ReadingBlock 和 Section 锚点。
- 发现的新 node 要写回 state；Section 不需要发现状态。

## 5. index：把原始文档变成可读、可检索、可追溯的数据

目标：从原始资源生成结构、正文块、检索块、图谱素材和权限数据。

流程：
1. `ResourceIndexer` 接到 document ready 事件。
2. `constructor` 负责把原文拆成 revision、structure、reading blocks、retrieval chunks、graph build source。
3. `ContextualTextIndexer` 负责上下文增强的检索文本。
4. `KnowledgeGraphExtractor` 负责从 graph build source 提取关系。
5. 写入 qdrant、neo4j、mongo 的各自持久化目标。
6. ACL 也在这里同步刷新。

对应文件：
- `src/rag/application/rag/index/resource_indexer.py`
- `src/rag/application/rag/index/contextualize.py`
- `src/rag/application/rag/index/constructor/structure.py`
- `src/rag/application/rag/index/constructor/revisions.py`
- `src/rag/application/rag/index/constructor/reading_blocks.py`
- `src/rag/application/rag/index/constructor/retrieval_chunks.py`
- `src/rag/application/rag/index/constructor/source_refs.py`
- `src/rag/application/rag/index/constructor/graph_merge.py`
- `src/rag/application/rag/index/graph/extractor.py`
- `src/rag/application/rag/index/graph/windows.py`
- `src/rag/core/persistence/mongo/writers/resource_index_writer.py`
- `src/rag/core/persistence/qdrant/writers/retrieval_index_writer.py`
- `src/rag/core/persistence/neo4j/writers/knowledge_graph_writer.py`
- `src/rag/application/rag/acl/resource_acl_refresher.py`

### reviewer 重点
- `retrieval_chunks` 是给检索用的，不等于 graph 抽取输入。
- `reading_blocks` 是检索命中提升和图谱证据的可读单元，不要混入 page/section 确定性 READ。
- 不要让 index 阶段偷偷承担 read/expand 的职责。
