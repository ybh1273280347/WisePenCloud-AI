# WisePen RAG Service v2 架构

本文档是 v2 的稳定架构基线，约束 `application/rag` 的能力边界、依赖方向和跨层契约。实现细节、迁移进度和验收项记录在 [TODO.md](./TODO.md)，不得用临时实现反向修改这里的职责定义。

## 1. 核心目标

RAG 服务负责把权威资源构造成可检索、可阅读、可扩展、可核验的私有知识，并在每次访问时执行统一 ACL。

Agent 的知识阅读流程是：

```text
LOCATE -> READ -> EXPAND -> VERIFY
```

- `LOCATE` 发现与问题相关的阅读入口。
- `READ` 获取文档结构和权威正文。
- `EXPAND` 从已知节点继续探索有证据的知识关系。
- `VERIFY` 把检索或关系结果核验并回到原始证据。

该流程描述用户能力，不表示 Python 包必须按箭头顺序互相导入。确定性 page/section 读取可以绕过 LOCATE，任何输出在需要证据时都可以进入 VERIFY。

为了支撑这四个读取动作，application 还包含：

- `INDEX`：构建和发布所有派生数据。
- `ACL`：计算、同步和执行资源访问权限。

## 2. application/rag 目录

`application/rag` 只包含以下六个业务目录：

```text
application/rag/
├── index/
├── locate/
├── read/
├── expand/
├── verify/
└── acl/
```

目录名表达能力，不表达后端、算法或临时处理阶段。不得在同级重新建立 `ingestion`、`retrieval`、`section_navigation`、`graph_extraction`、`graph_projection`、`evidence`、`models`、`services` 或 `common` 等目录。

写入目录命名为 `index`，原因是它和 `locate/read/expand/verify` 一样表示动作与能力。`indexer` 是执行者名称，只能用于确实负责编排一次索引写入的函数或对象，例如 `index_resource` 或 `ResourceIndexer`，不能成为装载所有写入逻辑的万能类。

## 3. 六个能力的职责

### 3.1 index

`index` 把上游权威资源转换为其他读取能力可消费的派生状态。

拥有：

- 文档完成事件对应的 application 用例。
- Markdown 结构解析和稳定原文坐标。
- Section、ReadingBlock、RetrievalChunk、SourceRef 的构建。
- contextual indexing 和检索索引写入。
- 图候选抽取、确定性校验、节点/关系合并和图发布。
- staged/applied revision、并发冲突、重试和幂等发布。
- 资源重建以及 Mongo、Qdrant、Neo4j 等派生数据的物理删除。
- `sectioned`、`flat_text`、`empty` 三种内容结构及其转换清理。

不拥有：

- 在线检索和排序。
- 图遍历与路径排序。
- Agent 探索提示或缺失原因装配。
- ACL 规则定义；写入权限字段时调用 `acl` 的公开能力。

`index` 可以在内部按结构解析、检索索引、图构建和 revision 发布拆文件，但这些只是同一写入能力的阶段，不能重新升级为同级 application 能力。

### 3.2 locate

`locate` 根据用户问题发现最值得阅读的 ReadingBlock 和 Section，并建立后续探索状态。

拥有：

- 语义查询 embedding、dense/BM25 混合召回和排序编排。
- applied revision 过滤和召回后的最终 ACL 过滤。
- 按 `(resource_id, reading_block_id)` 去重并选择入口。
- 将命中聚合为 Section 阅读入口和轻量 frontier。
- 创建 navigation state，记录用户、会话、根问题、已发现 Section 和已发现图节点。

不拥有：

- 内容与图谱写入。
- Section 全文读取。
- 图关系扩展。
- SourceRef 的最终证据真实性判断；该职责交给 `verify`。

### 3.3 read

`read` 负责所有结构和正文读取，并明确区分无状态读取与有状态阅读。

拥有：

- 获取 document structure，不夹带 page/section 正文。
- 按 page label 确定性读取正文。
- 按稳定 Section ID 确定性读取正文。
- 在 navigation state 内读取已发现 Section，并扩展 known sections。
- 返回有序 ReadingBlock 和 parent/previous/next/children frontier。

不拥有：

- 语义检索、rerank 或图抽取。
- 图关系遍历。
- 面向 Agent 的 `page_not_found`、`section_not_found`、`section_empty` 等业务文案。

无状态 structure/page/section 读取只依赖资源 ACL 和 applied revision，不要求先调用 `locate`。有状态 Section 阅读额外要求 Section 已被当前 navigation state 发现。

### 3.4 expand

`expand` 从 navigation state 中已发现的图节点进行有界关系探索。

拥有：

- 校验起点节点已经被当前 state 发现。
- relation type、方向、深度和结果数量约束。
- 图路径查询、基于当前问题的路径排序和新节点发现。
- 去除没有带来新节点的已知路径。
- 原子扩展 navigation state 的 known nodes。
- 返回节点、关系、路径及可继续阅读的来源 Section。

不拥有：

- 图抽取、节点规范化、关系合并或 Neo4j 写入；这些属于 `index`。
- 自然语言检索入口发现；这属于 `locate`。
- 关系 evidence 的最终回源核验；这属于 `verify`。

### 3.5 verify

`verify` 确认检索或图关系所引用的证据仍然属于当前可读的权威内容。

拥有：

- SourceRef 解析。
- resource/content revision 一致性检查。
- 原始 Markdown span 边界和证据文本核验。
- RetrievalChunk、ReadingBlock、Section、page 和 anchor 之间的回源关联。
- 结果返回前的最终 ACL 复查。
- 证据缺失、越界或 revision 冲突时阻止不完整结果返回。

不拥有：

- 召回、排序、Section 阅读或图遍历。
- 模型生成文本是否“回答了问题”的判断。
- Agent 如何展示部分结果、缺失项或继续探索的策略。

索引期间对模型抽取 evidence 的发布前校验仍由 `index` 负责，因为它作用于 staged revision。两者可以复用纯粹的 span/offset 领域规则，但 `index` 不应调用只面向 applied revision 的运行时 VERIFY 用例。

### 3.6 acl

`acl` 是独立业务能力，也是另外五个能力共同依赖的安全边界。

拥有：

- 从上游资源库读取权威 ACL 事实。
- owner、直接用户、资源排除、managed group、joined group 等规则计算。
- 本地 ACL 表示的写入和读取。
- Qdrant 与 Neo4j 权限字段同步。
- 单资源授权、批量资源过滤和后端查询权限条件构造。
- 不可访问与不存在对外不可区分的安全语义。

不拥有：

- 文档内容、检索候选或图路径的业务组装。
- 因方便某个后端而修改权威权限语义。

权限规则只能定义一次。Qdrant filter、Neo4j predicate 和最终回源校验必须来自同一组 ACL 语义，不能分别实现近似版本。

## 4. 能力协作

稳定依赖方向如下：

```text
index  ──────────────────────────────> acl

locate ───────────────> verify ─────> acl
  │
  └── creates navigation state

read ──> locate 的 state 访问契约
  ├────> verify
  └────> acl

expand -> locate 的 state 访问契约
  ├────> verify
  └────> acl
```

约束：

- `index` 不依赖 `locate/read/expand`，读取能力也不反向调用 `index`。
- `verify` 不依赖 `locate/read/expand`，否则会形成证据层吞并上层业务的循环。
- `acl` 不依赖其他五个能力。
- `read` 和 `expand` 可以依赖 `locate` 暴露的 navigation state 访问契约，但不能导入 locate 的检索、排序或结果组装实现。
- 六个目录只通过公开用例或明确的跨模块契约协作，不跨目录导入内部 helper、持久化 document 或临时 result model。

## 5. Navigation state

Navigation state 是 LOCATE、READ、EXPAND 协作所需的状态，不是第七个业务能力。

- `locate` 拥有 state 的创建语义和公开访问契约。
- `read` 只能校验并扩展 known sections。
- `expand` 只能校验并扩展 known nodes。
- state 必须绑定登录用户和 session，并保存根问题与必要的 revision 身份。
- known sections/nodes 必须原子扩展，不能由调用方整对象覆盖。
- 资源删除、ACL 撤销或 revision 更新后，state 不能绕过最终 ACL/revision 校验。
- Redis 只是状态存储 adapter，不决定 state 的业务语义。

只有当 navigation state 被多个 application 域共同使用时，才允许把其契约上移到更高层共享 domain/port；不能仅为了避免一次跨目录导入创建 `common`。

## 6. 数据与模型

### 6.1 业务事实

以下概念具有跨能力消费者，可以作为稳定领域契约，但必须按概念归属拆分，不能集中到一个全局 `models.py`：

- 内容结构：Section、ReadingBlock、RetrievalChunk、SourceRef、page、anchor、content revision。
- 导航状态：用户、session、root query、known sections、known nodes。
- 图事实：node、relation、path、evidence。
- 权限事实：resource ACL 和 permission scope。

这些契约应放在其真实 owner 或跨能力 domain 模块中。持久化 document、HTTP schema、Kafka payload 和 application result 不得冒充领域实体。

### 6.2 建模规则

- 字段必须有真实 producer 和 consumer。
- 只在跨模块、跨层或外部契约确实共享时定义模型。
- 单个函数内部的短生命周期组合不单独创建 model。
- 固定值集合使用枚举或受约束的字面值。
- 没有不可变、防误改或字典 key 要求时，集合使用 `list` 或 `dict`。
- 多返回值必须具名；禁止依赖位置含义的 tuple。
- HTTP/Kafka 校验模型属于 adapter，持久化模型属于 persistence，不能被 application 反向依赖。
- repository/port 接受和返回领域或用例语义，不暴露 Mongo/Qdrant/Neo4j 原生对象。

## 7. Revision 与证据不变量

所有六个能力共同遵守以下不变量：

- 原始 Markdown 是正文和证据坐标的唯一权威来源。
- offset 使用 Python 字符下标和左闭右开区间。
- `index` 先完整 stage，再发布 applied revision。
- `locate/read/expand/verify` 只读取 applied revision。
- contextual indexing 只能增强索引文本，不能修改 raw text 或 SourceRef。
- 检索和图关系返回前都必须落回当前 revision 的有效 SourceRef。
- 新 revision 不能被旧索引任务、旧图任务或旧 navigation state 覆盖。
- `flat_text` 和 `empty` 必须清除此前 sectioned revision 遗留的图数据。

## 8. 接口与错误边界

RAG 服务返回能力事实，不返回 Agent 业务解释。

- HTTP adapter 负责认证、请求 schema、平台响应包装和异常到错误码的映射。
- Kafka adapter 负责 payload 校验、重试分类和 offset 策略。
- application 用例遇到失败直接抛出语义明确的异常。
- 禁止用 `success/error/reason/message` 字段或局部变量逐层传导异常。
- 批量 page/section 读取返回实际存在且可读的 key；缺失 key 由调用方比较请求与返回集合。
- 合法但无正文的 Section 返回空 ReadingBlock 列表。
- `page_not_found`、`section_not_found`、`section_empty` 等面向模型的探索语义由 MCP/Agent adapter 组装。
- 资源不可访问、revision 不一致、证据损坏和依赖不可用属于真正失败，必须抛出。
- 对外错误不得泄漏不可访问资源是否存在、内部存储结构或依赖细节。

## 9. Adapter 与 persistence

HTTP、Kafka、Mongo、Qdrant、Neo4j、Redis、模型客户端都是六个能力外侧的实现边界。

```text
HTTP / Kafka
     │
     v
application/rag 六个能力
     │
     v
port / repository contract
     │
     v
Mongo / Qdrant / Neo4j / Redis / model clients
```

- adapter 可以依赖 application 的公开契约，application 不能依赖 adapter schema。
- persistence 实现 port，port 不能返回后端原生 document、point、record 或 driver session。
- Mongo/Qdrant/Neo4j/Redis schema 是内部实现，不是服务间兼容协议。
- collection、index、constraint、TTL、批量大小和并发数属于配置或实现细节，不用于命名 application 能力。
- API endpoint 不直接拼 repository 查询，也不在序列化阶段补做业务判断。

## 10. 命名规则

- 名称必须同时说明动作和对象，例如 `read_document_structure`、`read_pages`、`merge_candidate_graph`、`publish_resource_graph`。
- `projection` 只表示从明确上游结构到明确目标结构的字段/结构映射。
- 图抽取、规范化、合并和发布就是 extraction、normalization、merge、publish，不能合并命名为 graph projection。
- `snapshot` 只在确实表达某时刻不可变整体视图时使用；结构获取和正文读取不得使用该词。
- `manager`、`processor`、`materializer`、`service`、`utils`、`common` 不能替代真实职责名。
- 类只在需要维护依赖或状态时存在；单一无状态动作优先使用直接函数。
- 抽象名称如果必须靠长 docstring 才能解释，先拆职责，再重新命名。

## 11. 架构变更规则

以下变化必须先修改本文档并完成边界评审：

- 新增、删除或合并 `application/rag` 的六个能力目录。
- 将写图职责移出 `index`，或将图写入与图遍历重新混合。
- 将 structure 获取与 page/section 正文读取重新合并为 snapshot。
- 让 RAG application 开始生成 Agent 探索原因、展示文案或部分结果策略。
- 让某个存储后端定义 ACL、revision 或证据语义。
- 引入跨能力全局 models/common/utils，或让 domain/repository 反向依赖 adapter/application 临时模型。
- 改变原文 offset、applied revision、最终 ACL 复查或 SourceRef 回源不变量。

其余实现选择可以在不修改本文档的情况下演进，但必须保持六个能力的输入、输出、异常、数据副作用和依赖方向不变。
