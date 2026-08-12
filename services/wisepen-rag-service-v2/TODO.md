# WisePen RAG Service v2 能力迁移清单

本文档记录 v1 已经承担的能力、v2 必须重新划定的边界，以及逐项验收方法。它不是旧目录结构的搬运清单。迁移的判定标准是外部可观察行为、数据语义和一致性约束等价，而不是类名、模型名或存储结构相同。

## 0. 重写约束

- [ ] 先冻结 v2 的能力边界，再设计包结构；不得从 v1 文件名反推模块。
- [ ] 以“定位、结构读取、内容读取、关系扩展、证据核验”为业务动作命名模块和入口。
- [ ] 禁止继续使用不能说明产物的抽象命名，例如 `snapshot`、`materializer`、`manager`、`processor` 或没有映射对象的裸 `projector`。
- [ ] 只有“把一种既有上游结构映射成另一种明确目标结构”时才使用 `projector`/`projection`。知识图谱的抽取、规范化、合并和写入应分别按实际动作命名，不能统称为 graph projection。
- [ ] 文档结构获取与正文读取必须是两个独立能力。结构接口不得顺带返回 page/section 正文，正文读取不得依赖语义检索或知识图谱。
- [ ] RAG 只提供检索、读取、图遍历等能力事实，不装配 Agent 的探索语义。`page_not_found`、`section_not_found`、`section_empty` 等面向模型的原因由 MCP/Agent 调用方根据 RAG 结果生成。
- [ ] 资源不可访问、revision 不一致、依赖失败等真正的失败直接抛出明确异常；禁止用 `error`、`reason`、`success` 变量逐层传递错误。
- [ ] 批量读取正常返回“实际读到的 key -> 内容”。未返回的请求 key 由调用方解释；无正文的合法 Section 返回空内容，不伪装成异常。
- [ ] 固定值集合使用枚举或受约束的字面值，不用任意字符串。
- [ ] 没有不可变、防误改或作为字典 key 的明确要求时，集合优先使用 `list`/`dict`，不把 `tuple` 当默认容器。
- [ ] 只在跨模块、跨层或外部契约真实共享时定义模型。模块私有的短生命周期数据就地使用，不为单一函数创建 `models.py`。
- [ ] 请求校验只发生在 HTTP/Kafka 边界；application 内部不重复包装同构 request/result model。
- [ ] 不为兼容 v1 内部类型保留转发类、别名或双轨逻辑。确需兼容的只能是已确认的外部 HTTP/Kafka 契约。
- [ ] 注释解释权限、offset、revision、幂等和降级边界，不复述代码动作。

### 0.1 稳定架构基线

- [ ] `application/rag` 的六个能力边界、依赖方向、模型归属和错误边界以 [Architecture.md](./Architecture.md) 为准；TODO 只记录迁移和验收进度，不复制架构正文。

## 1. 迁移前契约冻结

- [ ] 从当前代码、MCP 调用方和线上 payload 三方核对 HTTP 契约；README 只能作为线索，不能作为唯一规格。
- [ ] 确认 `locate` 当前最终请求字段：`session_id`、`semantic_query`、可选 `lexical_query`、`max_results`。记录旧 `query` 字段是否仍有真实调用方。
- [ ] 确认结构读取、页读取、章节读取三个 HTTP 路径及当前调用方，决定 v2 是原路径替换还是显式版本化。
- [ ] 确认 `sections`、`cypher` 的现行路径、字段、数量上限和响应字段。
- [ ] 确认统一响应包装 `R` 是否属于平台强制契约；application 层不得依赖该包装。
- [ ] 确认 Kafka 三类事件的真实 topic、字段、容错规则与 offset 提交策略。
- [ ] 为每个外部入口保存一组脱敏的 v1 请求/响应 fixture，作为 v2 contract test 输入。
- [ ] 列出 MCP/Agent 实际消费的每个响应字段；没有消费者的字段不自动迁移。
- [ ] 决定派生数据是从权威 Markdown 和事实事件全量重建，还是迁移旧存储。默认优先重建，禁止把旧 Mongo/Qdrant/Neo4j schema 误当公共契约。

## 2. 文档接入与版本发布

### 2.1 文档完成事件

- [ ] 消费文档完成事件：`resourceId` 非空、`version` 为大于等于 1 的严格整数、`content` 为 Markdown 字符串。
- [ ] 拒绝非法事件并抛出可重试/不可重试的明确异常；不得返回携带错误原因的伪成功对象。
- [ ] 同一资源的低版本事件不能覆盖已应用的高版本。
- [ ] 相同资源、版本和内容的重复事件必须幂等收敛。
- [ ] 以资源 ID、文档版本、内容 hash 和 schema version 标识内容 revision。
- [ ] 写入完整 revision 后才能切换为 applied；查询只能看到 applied revision。
- [ ] 向量写入失败、图谱构建失败或并发出现新 revision 时，不得暴露半成品 revision。
- [ ] 新 revision 发布后清理旧 revision 的内容、向量和图数据；清理可安全重试。
- [ ] 对内容不变且生成配置不变的派生结果支持复用，复用 key 必须包含实际影响输出的输入和配置。

### 2.2 三种内容结构

- [ ] `sectioned`：解析标题层级、页、锚点、原文 offset、Section、ReadingBlock、RetrievalChunk 和 SourceRef。
- [ ] `flat_text`：没有有效标题但存在正文时仍可检索和按块读取。
- [ ] `empty`：没有有效正文时发布一个可识别的空 revision，并清理旧索引与旧图谱。
- [ ] `flat_text` 的父级 ReadingBlock 保留当前 6000 字符、无重叠行为，除非基准测试明确批准修改。
- [ ] `flat_text` 的 RetrievalChunk 保留当前 800 字符、100 字符重叠行为，除非基准测试明确批准修改。
- [ ] flat text 的合成标题只服务导航，不进入 embedding、BM25 或 rerank 文本。
- [ ] `flat_text` 和 `empty` 跳过 contextual indexing 与图抽取，并以 revision 为单位幂等记录跳过结果。
- [ ] 覆盖 `sectioned -> flat_text -> empty` 及反向转换；切换后不得残留旧 Section、向量、mention、relation 或孤立图节点。

## 3. 内容结构与证据坐标

### 3.1 结构解析

- [ ] 原始 Markdown 是正文和证据坐标的唯一权威来源。
- [ ] 所有 `start`/`end` 使用 Python 字符下标和左闭右开区间，禁止混用字节 offset、UTF-16 offset 或 token offset。
- [ ] 解析标题树并保留：稳定 Section ID、title、level、parent、ordinal、section path、直属正文范围和子树范围。
- [ ] 解析页标签、页范围和锚点；页标记本身不得污染检索正文。
- [ ] 长 Section 拆成有序 ReadingBlock；同一 Section 可以合法拥有多个 ReadingBlock。
- [ ] ReadingBlock 保留可回到原文的 source spans、page labels 和 anchor labels。
- [ ] RetrievalChunk 是评分单位，保留所属 ReadingBlock、Section、原始文本、索引文本和 source spans。
- [ ] SourceRef 能把每个命中 chunk 精确映射回原始 Markdown 的连续证据。
- [ ] Section、ReadingBlock、RetrievalChunk、SourceRef 的稳定 ID 由真实身份字段和 span 决定，不依赖进程内顺序或随机 UUID。

### 3.2 Contextual indexing

- [ ] contextual text 只增强 RetrievalChunk 的 `index_text`，不得修改 raw text、Section 范围或 SourceRef。
- [ ] 上下文至少基于标题路径、Section 直属正文预览和所属 ReadingBlock；重新核对实际 prompt 后冻结输入。
- [ ] 生成缓存 key 包含 prompt、模型配置、输入内容和 schema 版本。
- [ ] contextual indexing 失败时按既定发布策略抛出或跳过，不能把错误字符串写进索引正文。

## 4. 资源结构获取与确定性正文读取

### 4.1 文档结构获取

- [ ] 提供独立的 document structure 能力，返回资源、版本、applied revision、`structure_mode`、总字符数、页目录和 Section 树。
- [ ] structure 返回轻量导航信息，不返回 page/section 正文，不触发 embedding、rerank 或图查询。
- [ ] Section 节点只保留调用方确实用于导航的字段；不沿用笼统的 snapshot/content item 模型。
- [ ] 结构读取必须经过最终 ACL 校验，并只读取 applied revision。

### 4.2 页正文读取

- [ ] 按一个或多个 page label 确定性读取正文，保持当前单次 1-20 个标签的限制，除非契约冻结阶段另有结论。
- [ ] 返回实际存在页的映射和精确正文窗口；不得返回 `kind` 或 Agent 使用的 `reason`。
- [ ] 一个合法存在但无正文的页返回空内容；不存在的标签不进入结果映射，由调用方比较请求集合与返回集合。
- [ ] 每个正文窗口只保留真实消费的字段：文本、原文 start/end、source spans、page/section/anchor 标识。

### 4.3 Section 正文读取

- [ ] 按一个或多个稳定 Section ID 确定性读取正文，保持当前单次 1-20 个 ID 的限制，除非契约冻结阶段另有结论。
- [ ] 返回实际存在 Section 的映射及其有序 ReadingBlock；不得返回 `kind` 或 Agent 使用的 `reason`。
- [ ] 合法 Section 没有直属正文时返回空 ReadingBlock 列表；调用方决定如何向模型说明。
- [ ] 不存在的 Section ID 不进入结果映射；资源整体不可读、revision 损坏或依赖不可用则抛出对应异常。
- [ ] 页读取和 Section 读取不依赖知识导航 state，不能要求先 `locate`。

## 5. ACL 安全边界

### 5.1 ACL 事实与规则

- [ ] 消费 ACL 重算事件，并从 Java 资源库读取权威 ACL；事件本身只提供资源 ID。
- [ ] 本地 ACL 数据是权威规则的检索侧表示，不是新的授权来源。
- [ ] 保留 VIEW 权限语义和以下优先级：资源直接排除高于群组授予；owner 直接允许；直接用户 allow；群组角色和资源群组规则按现行真值表计算。
- [ ] managed group 的 OWNER/ADMIN 授权、joined group 的默认可读/显式可读/排除规则必须逐项写成测试。
- [ ] 批量过滤时，本地 ACL 缺失不能被解释成授权。
- [ ] 索引/同步阶段允许按当前约定回源权威 ACL，但失败必须显式抛出。

### 5.2 全链路执行

- [ ] 身份只来自登录态与服务端 SecurityContext，HTTP body 不接受 user ID 或群组角色。
- [ ] 同一权限语义下推到 Qdrant 过滤、Neo4j 过滤和最终 Mongo 回源。
- [ ] 检索候选在后端过滤后仍要执行最终权威 ACL 校验。
- [ ] 返回正文或 evidence 前立即再次校验 ACL，防止检索后权限变化导致泄漏。
- [ ] 对外不可区分“资源不存在”和“资源存在但无权访问”。
- [ ] ACL 变更同步更新本地 ACL、Qdrant payload 和 Neo4j Resource 节点，并可幂等重试。
- [ ] 用同一组 ACL 真值表测试 Mongo 读取、Qdrant 召回、Neo4j 遍历和最终证据读取，禁止四处各写一套相近逻辑。

## 6. 混合检索与排序

- [ ] `semantic_query` 驱动 query embedding 和 rerank。
- [ ] `lexical_query` 驱动 BM25；未提供时回退为 `semantic_query`。
- [ ] 每次 locate 只生成一个 query embedding。
- [ ] Qdrant 同时执行 dense 与 native BM25 召回，保留现行 candidate limit 和融合语义，配置值需在迁移时核对。
- [ ] 检索过滤必须包含权限范围和当前 applied revision。
- [ ] 排序输入保留 dense、lexical 及其他当前实际使用的 score signals；禁止迁移无人消费的中间 score model。
- [ ] rerank 使用语义查询，不把词法关键词误作完整问题。
- [ ] 保留 relevant/uncertain/irrelevant 三档判定以及当前 low=0.2、high=0.6、uncertain limit=3 的行为，除非离线评测批准修改。
- [ ] 排序后按 `(resource_id, reading_block_id)` 去重，再截取 top-k。
- [ ] 不得按 Section ID 去重；同一 Section 的多个 ReadingBlock 可以同时成为结果。
- [ ] 只返回仍属于 applied revision 且能完整回源 SourceRef 和 ReadingBlock 的候选；回源不完整时抛出数据一致性异常，不能返回半条 evidence。

## 7. LOCATE：发现阅读入口

- [ ] locate 输入包含 session、语义查询、可选词法查询和结果上限；所有长度/数量约束只在接口边界校验一次。
- [ ] 混合检索只用于发现入口，不把 RetrievalChunk 直接当成完整阅读结果。
- [ ] 命中回源到 ReadingBlock 和 Section，并构造当前 Section 的阅读视图。
- [ ] 阅读视图包含当前 Section、命中 evidence、有序 ReadingBlock 和轻量 frontier。
- [ ] frontier 仅包含 parent、previous、next、children 的导航信息，不预加载相邻正文。
- [ ] 从命中 SourceRef 解析可见知识节点，创建 navigation state。
- [ ] locate 的 sources 按 Section 聚合时不得丢失同 Section 不同 ReadingBlock 的 evidence。
- [ ] 响应字段逐个以 MCP 消费为依据确认；不要为“以后可能有用”添加 metadata。

## 8. READ：有状态 Section 阅读

- [ ] `sections` 只能读取当前 navigation state 已发现的 Section ID。
- [ ] 请求保持当前 1-12 个 Section ID 上限，除非契约冻结阶段批准修改。
- [ ] 返回 Section 的完整有序 ReadingBlock 和下一层 frontier。
- [ ] 新发现的 frontier Section 原子加入 known sections，避免并发请求覆盖状态。
- [ ] 读取前后均校验 state 所属用户、session 和资源 ACL。
- [ ] 未发现 Section 的请求使 state 失效或抛出明确的越界异常，不能静默扩大读取范围。
- [ ] 本能力与“按 Section ID 直接读取资源正文”是两个不同入口：前者受 navigation state 约束，后者只受资源 ACL 和 applied revision 约束。

## 9. EXPAND：知识关系扩展

### 9.1 图谱抽取

- [ ] 从 ReadingBlock 级证据窗口抽取图谱，不从 RetrievalChunk 碎片直接抽取。
- [ ] 父上下文可以由相邻 block 尾部/头部和滑动窗口组成，但不得改变 evidence 的原文坐标。
- [ ] 使用已验证的 GraphRAG SDK/引擎完成候选抽取，不自行实现基础图抽取协议。
- [ ] 支持 Entity、Resource、ExternalSource 三类真实节点，以及现行 entity types。
- [ ] 支持现行关系集合：`MENTIONS`、`ABOUT`、`RELATED_TO`、`PART_OF`、`USES`、`PRODUCES`、`DEPENDS_ON`、`DERIVED_FROM`、`IMPLEMENTS`、`APPLIES_TO`、`CAUSES`、`COMPARES_WITH`、`CONTRADICTS`、`EXTENDS`、`SUPERSEDES`、`LOCATED_IN`、`AUTHORED_BY`、`DEFINES`、`EXPLAINS`、`EXAMPLE_OF`、`REQUIRES`、`CITES`、`PUBLISHED_IN`、`USES_DATASET`、`USES_METHOD`、`SUPPLEMENTS`、`RETRACTS`。
- [ ] 核对并保留 core/learning/scholarly relation profile 对允许关系的约束。
- [ ] 抽取结果支持 affirmed/negated/conditional/uncertain assertion；当前只发布 affirmed 的行为必须有测试。
- [ ] `RELATED_TO` 必须携带具体 predicate，不能把所有关系退化为无语义关联。
- [ ] Resource 节点必须指向当前资源，禁止模型凭空关联另一个私有资源。
- [ ] 每条 relation 的 evidence quote 必须是抽取窗口中的连续原文，并精确映射到 SourceRef。
- [ ] 对节点类型、关系类型、端点组合、evidence 和资源归属做确定性校验；非法候选直接丢弃或使本次构建失败，策略需显式固定。
- [ ] 原始候选图缓存 key 包含 prompt、schema、SDK、模型配置和完整抽取窗口；缓存命中后仍执行当前版本的确定性校验。

### 9.2 图谱构建与发布

- [ ] 将候选节点名称做 NFKC、大小写和空白规范化，并生成稳定节点 ID。
- [ ] 合并等价节点，但保留来源证据；不要创建名为 `KnowledgeGraphProjection` 的二次业务实体。
- [ ] 按规范化端点、关系类型和 predicate 聚合等价关系，去重并累积 evidence。
- [ ] 建立 Resource、知识节点、relation、MENTIONS 与 SourceRef/Section 之间的可追溯联系。
- [ ] 长耗时抽取前先使旧图 revision 不可见；完成时再次确认内容 revision 仍是当前 applied revision。
- [ ] 并发出现更新 revision 时放弃旧构建结果，不覆盖新图。
- [ ] 发布新图后删除旧 relation、mention 和无其他资源引用的孤立节点。
- [ ] `flat_text`/`empty` revision 必须清除旧图并幂等记录 skipped，不发布空壳图谱。
- [ ] Resource 节点 ACL 与本地 ACL 更新同步。

### 9.3 有界图遍历

- [ ] `cypher` 只能从 navigation state 已发现的 node ID 出发。
- [ ] 保持 node IDs 1-16、relation types 最多 16、depth 1-2、results 1-20 的现行边界，除非契约冻结阶段批准修改。
- [ ] 支持 `in`、`out`、`both` 方向和可选 relation type 过滤。
- [ ] 路径排序使用请求 query；未提供时回退到 state 的 root query。
- [ ] 已知路径如果没有发现新节点则不返回，避免重复消耗上下文。
- [ ] 返回去重 nodes、edges、有序 paths 和关系 evidence 对应的 Section sources。
- [ ] 新发现节点原子写回 state；图返回的每条 evidence 在返回前重新校验资源 ACL 和 applied revision。

## 10. VERIFY：证据核验

- [ ] 所有检索命中和图关系都能落回可读 Section、ReadingBlock 与原始 Markdown span。
- [ ] evidence 响应保留实际被调用方使用的 content、ref ID、chunk ID、page labels 和 anchor labels。
- [ ] evidence 文本必须等于权威 Markdown 对应 span，不能使用 contextual text、模型改写文本或缓存摘要替代。
- [ ] 资源 revision 变化后，旧 state 不能把旧 evidence 当作当前内容返回。
- [ ] 证据缺失、span 越界或内容不一致是服务数据错误，必须抛出并阻止该结果返回。

## 11. Navigation state

- [ ] locate 创建以 `state_id` 标识的状态，保存 user、session、root query、known sections、known nodes 和创建时涉及的资源 revision。
- [ ] state 默认 TTL 保留当前 24 小时行为，实际配置名在实现时冻结。
- [ ] 后续请求必须同时匹配 state ID、登录用户和 session ID。
- [ ] 区分状态不存在/过期、状态因越界访问失效、依赖不可用三类异常。
- [ ] known sections 和 known nodes 的扩展使用原子更新，支持同一 state 并发请求。
- [ ] 资源删除、ACL 撤销或 revision 更新后，旧 state 不能绕过最终读取校验。
- [ ] 明确删除事件是主动失效相关 state，还是依靠最终校验加 TTL；无论选择哪种方案，都要有删除后不可读测试。

## 12. 资源删除

- [ ] 消费资源物理删除事件，从 `typedResourceIds: dict[str, list[str]]` 展平并去重资源 ID。
- [ ] 清理资源的内容 revision、结构、ReadingBlock、RetrievalChunk、SourceRef、contextual cache 和图抽取 cache。
- [ ] 清理 Qdrant dense/BM25 points。
- [ ] 清理 Neo4j Resource、mentions、relations 以及因此失去引用的孤立节点。
- [ ] 清理本地 ACL 数据。
- [ ] 按已冻结策略清理或阻断 Redis navigation state。
- [ ] 删除流程可重复执行；部分后端失败时抛出并重试，不能用汇总 reason 掩盖未删除后端。
- [ ] 删除只作用于 RAG 派生数据，不删除上游业务资源。

## 13. API 与错误边界

- [ ] HTTP 层负责 schema 校验、认证、错误码映射和平台响应包装；application 层只暴露业务参数和返回值。
- [ ] Kafka adapter 负责 payload 校验和 retry/offset 策略；application handler 直接抛出失败。
- [ ] 定义少量、具体、可处理的异常：参数错误、资源不可读、navigation state 不存在、state 越界失效、revision 冲突、派生数据不一致、依赖不可用。
- [ ] 资源读取错误不能复用 `NAVIGATION_STATE_NOT_FOUND` 等无关错误码。
- [ ] MCP/Agent adapter 捕获 RAG 异常，并决定是中断、返回部分结果还是生成模型可理解的探索提示。
- [ ] RAG 响应中不出现 `reason=page_not_found/section_not_found/section_empty`，也不为此定义 application model。
- [ ] 对外错误不泄漏资源是否真实存在、内部存储名、凭证、查询语句或堆栈。
- [ ] 所有批量能力明确部分成功语义：成功项正常返回；系统性失败抛出；缺失 key 由调用方集合差异识别。

## 14. 包与模型治理

- [ ] `application/rag` 只建立 `index`、`locate`、`read`、`expand`、`verify`、`acl` 六个业务目录；新增第七个目录前必须证明它是独立业务能力，而非实现阶段或共享杂物。
- [ ] 六个目录只通过明确的公开用例或契约协作，不跨目录导入内部 helper、持久化 document 或临时 result model。
- [ ] 禁止建立承接所有逻辑的 `application/rag/models.py`、`services.py`、`utils.py` 或 `common.py`。
- [ ] 跨层 DTO 放在拥有契约的一侧：HTTP/Kafka schema 属于 adapter，持久化记录属于 repository，业务实体只保留稳定业务身份和不变量。
- [ ] 同一字段结构只使用一次时就地表达；只有出现真实共享消费者才提取命名类型。
- [ ] 函数返回多个同属一个概念且会继续共同传递的数据时才定义对象；局部解包即可结束的数据不创建 result model。
- [ ] 多值结果优先返回具名 `dict` 或语义明确的列表，不返回需要靠位置猜含义的 tuple。
- [ ] 不把所有 list 改成 tuple 来制造“领域模型感”；只有作为 hash key 或必须防止修改的值才使用 tuple/frozen。
- [ ] 公共名称必须能从名字判断动作和对象，例如 `read_document_structure`、`read_pages`、`merge_candidate_graph`、`publish_resource_graph`。
- [ ] 抽象名称一旦需要靠长 docstring 才能解释职责，先拆模块和流程，再命名。
- [ ] package `__init__` 只导出真实稳定边界，不导出测试便利函数或内部 helper。

## 15. 存储与运行能力

- [ ] Mongo（或替代存储）保存 applied/staged content revision、结构、正文块、SourceRef、ACL 和可复用派生结果。
- [ ] Qdrant（或替代检索后端）支持 dense、native BM25、ACL payload、revision filter 和幂等 upsert/delete。
- [ ] Neo4j（或替代图后端）支持有证据的关系、资源 ACL、有界遍历和 revision 隔离。
- [ ] Redis（或替代状态后端）支持 TTL、用户/session 隔离和 known 集合原子扩展。
- [ ] 启动时检查/创建所需 collection、index 和 constraint；schema 迁移失败不得带病启动。
- [ ] 保留健康检查、OpenAPI 文档、服务发现和配置中心接入。
- [ ] 配置覆盖 embedding、reranker、图抽取模型、Kafka、Mongo、Qdrant、Neo4j、Redis、阈值、并发和 TTL。
- [ ] 密钥不进入日志、异常和持久化派生输入；模型/cache profile 只保存不可逆配置指纹。
- [ ] 关键流程记录 resource、revision、stage、耗时、数量和最终动作，避免记录全文或私有 evidence。
- [ ] 建立 indexing、retrieval、graph、ACL、deletion 的成功率、延迟、重试和积压指标。

## 16. 行为验收矩阵

### 16.1 单元与契约测试

- [ ] Markdown 标题、嵌套标题、无标题、空文档、页标记、锚点、Unicode 字符的 offset golden tests。
- [ ] Section/ReadingBlock/RetrievalChunk/SourceRef 稳定 ID 与精确回源测试。
- [ ] page/section 批量读取覆盖：全部存在、部分缺失、合法空内容、无权限、revision 损坏。
- [ ] 验证 RAG 返回能力事实，MCP/Agent 独立生成 missing/empty 的模型语义。
- [ ] semantic/lexical query 分工、BM25 回退、单次 embedding、融合、rerank 和阈值测试。
- [ ] 同 Section 多 ReadingBlock 保留、跨 chunk 同 ReadingBlock 去重测试。
- [ ] graph 候选校验、evidence 映射、canonicalization、关系聚合、缓存复用和缓存重校验测试。
- [ ] navigation state 用户/session 隔离、TTL、越界失效、并发原子扩展测试。
- [ ] 全 ACL 真值表在检索、正文读取、图遍历和 evidence 返回四条链路上参数化执行。
- [ ] HTTP schema/error mapping 与 Kafka validation/retry contract tests。

### 16.2 一致性与故障测试

- [ ] 重复文档事件、乱序版本、同版本不同内容、构建中出现新版本、发布后清旧版本。
- [ ] Mongo stage 成功但 Qdrant 失败、Qdrant 成功但 apply 失败、图构建失败、ACL 同步部分失败后的重试收敛。
- [ ] `sectioned`、`flat_text`、`empty` 六种双向切换后的存储残留检查。
- [ ] 资源删除在每个后端分别失败后的重试，以及删除后旧 navigation state 不可读。
- [ ] ACL 在检索后、回源前被撤销时不得返回正文。
- [ ] evidence span 越界、SourceRef 丢失、revision 不匹配时不得返回部分伪证据。

### 16.3 v1/v2 对照

- [ ] 使用同一批真实脱敏文档分别构建 v1/v2，比较结构模式、Section 树、原文范围、ReadingBlock、检索入口和 evidence。
- [ ] 对固定 query 集比较 top-k ReadingBlock、Section 覆盖、相关性档位和 ACL 结果；允许分数浮动，但差异必须有评测依据。
- [ ] 对固定图抽取输入比较有效节点、关系、证据覆盖和非法候选拦截率；不要求内部对象或 ID 格式与 v1 相同。
- [ ] 对 document structure、page read、section read、locate、sections、cypher 保存端到端 golden fixtures。
- [ ] 逐项记录有意变更；没有记录和批准的行为差异一律视为能力漂移。
- [ ] 编译、静态检查、单元测试、集成测试和 `git diff --check` 全部通过。

## 17. 上线与回滚

- [ ] 为 v2 使用独立的 Mongo collection、Qdrant collection、Neo4j revision namespace 和 Redis key prefix，避免写坏 v1 数据。
- [ ] 从权威内容源回放文档与 ACL 事件，完成全量重建并核对资源数、revision 数、向量数和图数据覆盖率。
- [ ] 在不影响调用方的前提下做 shadow read，对比 v1/v2 结果、错误率、延迟和权限判定。
- [ ] 切流前确认 MCP/Agent 已接管缺失页、缺失 Section、空 Section 等探索语义装配。
- [ ] 分阶段切换 structure/read、locate/read、graph traversal，不要求所有能力同一时刻切换。
- [ ] 保留可立即回到 v1 的路由开关；回滚不依赖把 v2 派生数据反写 v1。
- [ ] 切流后观察 Kafka lag、索引失败、ACL 拒绝率、无证据结果、state 失效率和后端延迟。
- [ ] 稳定期结束且审计通过后再停止 v1 消费和清理 v1 派生数据。

## 18. 完成定义

- [ ] 上述每项能力都有明确 owner、输入、输出、异常、持久化副作用和自动化测试。
- [ ] v2 代码中不存在为复刻 v1 而保留的 `snapshot`、伪 graph projection、Agent reason model 或位置 tuple。
- [ ] RAG、MCP/Agent、存储 adapter 的职责边界能从公开函数和包名直接读懂，无需依赖架构口头解释。
- [ ] 所有外部兼容项都有真实调用方证据；所有有意不兼容项都有迁移记录。
- [ ] v1/v2 对照报告中不存在未解释的权限、证据、revision、读取或检索行为差异。
