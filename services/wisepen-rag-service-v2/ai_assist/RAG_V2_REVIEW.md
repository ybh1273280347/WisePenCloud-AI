# RAG v2 review guide

这份文档是给人类 reviewer 看的：按 `locate / read / verify / expand / index` 五个模块看能力，不看实现细节花活。

## 1. locate：先找“可以继续读”的入口

目标：从问题里找到一组可信的 section 入口和 graph 节点，作为后续阅读的起点。

流程：
1. 接口接收 `semantic_query`、可选 `lexical_query`、资源白名单和 `max_results`。
2. `ReadingCandidateLocator` 先做召回，再做排序。
3. 排序后先去重，再做回源校验。
4. 校验通过后，补出 section frontier，写入 navigation state。
5. 返回 `state_id`、排序决策、graph nodes 和 section 入口。

对应文件：
- `src/rag/api/endpoints/locate.py`
- `src/rag/api/schemas/locate.py`
- `src/rag/application/rag/locate/candidate_locator.py`
- `src/rag/application/rag/locate/__init__.py`
- `src/rag/domain/repositories/qdrant/candidate_searcher.py`
- `src/rag/domain/repositories/neo4j/mention_lookup.py`
- `src/rag/application/rag/verify/evidence_verifier.py`
- `src/rag/domain/repositories/mongo/readers/applied_structure.py`
- `src/rag/domain/repositories/redis/navigation_state_store.py`

### reviewer 重点
- 有没有只返回“候选”而没有变成“可继续阅读入口”。
- section frontier 有没有保留 parent / previous / next / children。
- 排序和核验是不是在正确边界内完成。

## 2. read：直接读文档结构、页、section 正文

目标：不经过图谱，不经过检索，直接回答“这个资源长什么样、某一页/某一 section 里有什么”。

流程：
1. `getDocumentStructure` 先拿 applied revision。
2. 结构只返回页面和 section 树，不读正文。
3. `getPageContent` 按页读正文窗口。
4. `getSectionContent` 按 section 读正文块和 frontier。
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
- `src/rag/application/rag/verify/evidence_verifier.py`
- `src/rag/application/rag/verify/__init__.py`
- `src/rag/core/persistence/mongo/readers/evidence.py`
- `src/rag/domain/repositories/mongo/readers/evidence.py`

### reviewer 重点
- 这里是“核验”，不是“排序”。
- 不要把业务语义 reason 塞进 verifier 里。
- graph 引用和 locate 候选都要能在这里闭环。

## 4. expand：沿标题树或图谱继续探索

目标：把已经发现的 section / node 继续展开成可读、可探索的新入口。

流程：
1. `expandSections` 读取已发现 section 的正文和 frontier。
2. 返回完整 `SectionView`，里面有 section、reading blocks、frontier 和 evidence。
3. `expandGraph` 从已知 node 出发找路径、排序、核验证据。
4. 现在 graph 的 evidence 也会回补成 `SectionView`，并写回 navigation state。
5. 所以 graph 扩展后，调用方可以继续沿着证据所在 section 读标题树。

对应文件：
- `src/rag/api/endpoints/expand.py`
- `src/rag/api/schemas/expand.py`
- `src/rag/application/rag/expand/section_expander.py`
- `src/rag/application/rag/expand/graph_expander.py`
- `src/rag/application/rag/expand/__init__.py`
- `src/rag/domain/models/content.py`
- `src/rag/domain/repositories/redis/navigation_state_store.py`
- `src/rag/domain/repositories/neo4j/graph_traversal.py`

### reviewer 重点
- `expandSections` 是标题树能力主线，不是 read 的附属。
- `expandGraph` 不能只吐证据片段，必须保留可继续阅读的 section 上下文。
- 发现的新 section / node 要写回 state，不然能力只能看不能继续走。

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
- `reading_blocks` 是给图谱和回源用的，不要混成一锅。
- 不要让 index 阶段偷偷承担 read/expand 的职责。
