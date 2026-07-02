# Toolchain Architecture

> 一句话： WisePen Chat Service 的工具体系由若干业务域工具组成，它们通过 `search_ref`、`tfile_*`、`cnt_*` 和 URL 缓存形成稳定协作链。

实现入口：`src/chat/application/tools`
注册入口：`src/chat/container.py`

核心目标是：外界信息获取、文件解析、大文本缓存、证据定位、数学计算和 Skill 懒加载分别保持边界清晰，同时通过统一引用协议协作。

## 工具族复用指导原则

理解当前工具体系时，先记住三条：

1. **工具族之间默认保持解耦**
2. **工具族内部允许强复用**
3. **跨工具族复用只在核心体系边界上作为例外成立**

### 工具族之间默认解耦

如果某段实现只服务某个工具族内部语义，就不要因为“别的工具好像也能用”而直接把它当通用公共组件。

**例子**：不应把 `web_fetch` 的 HTML 清洗器当成一般性的 HTML to Markdown 公共能力，供任意非 web 工具直接复用。

### 工具族内部允许强复用

同一工具族内部，只要共享同一协议边界和运行时语义，就可以明确强复用。

**例子**：

- `academic_search` 是 `web_search` 的垂类拓展。
- `web_crawl` 是 `web_fetch` 的递归增强。

因此它们共享 `search_services/` 中的搜索编排、候选构建、URL 映射和抓取/清洗能力，属于有意设计，而不是默认要被拆散的耦合。

### 跨工具族复用是例外，不是一般情况

只有当被复用的对象本身已经承担了统一切面或核心协议职责时，跨工具族复用才成立。

**例子**：`document_parse` 对文档直链解析复用了 web URL 缓存。

这类复用之所以合理，本质上有两个原因：

1. `document_parse` 和 web 工具体系同属于模型的核心 IO 工具，天然共享一部分统一边界。
2. 这是架构与现实之间的必要妥协。如果不复用这条边界，文档直链经常都得先走一层 `web_fetch` 再转给 `document_parse`，这会让主链路明显变重，而且非常低效。

因此这里复用的是核心缓存边界，而不是 web 工具族内部的局部实现细节。

## 已注册工具

当前 `ToolRegistry` 注册 16 个工具：

| 分组 | 工具 |
| --- | --- |
| document | `document_parse` |
| math | `calculus_solver`、`linear_algebra_solver`、`equation_solver`、`stats_solver`、`expression_solver` |
| session | `tool_content_read`、`tool_content_sequential_read`、`get_historical_chat_messages` |
| web | `web_search`、`academic_search`、`web_fetch`、`web_crawl` |
| skill | `load_skill`、`load_skill_asset`、`create_skill` |

## Runtime 信封

工具执行统一经过：

```text
ToolInvocation
  -> JsonSchemaCheck / RequiredContextCheck / custom preflight hooks
  -> tool.execute(...)
  -> ToolOutputRenderer
  -> ToolOutputCache
  -> RenderToolResult
```

工具可以返回普通结构，也可以返回 `ToolReturn`。`ToolReturn` 的核心字段：

- `tag`：渲染成 XML 根节点，方便模型稳定读取。
- `visible_result`：直接给模型看的轻量结构化结果。
- `cacheable_texts`：大段正文、Markdown 或解析结果，不直接塞进 visible_result。

`ToolOutputCache` 会按总字符数决定是否把 `cacheable_texts` 内联；超出阈值时写入 `ToolContentStore`，返回 `cnt_*` receipt。后续读取必须使用 session 工具，而不是重新抓取或重新解析。

## 统一切面行为

所有 tool 都穿过同一组切面。工具文档和代码 review 必须按切面检查，而不是只看单个 `execute()`。

| 切面 | 入口 | 约束 |
| --- | --- | --- |
| Disclosure | `ToolRegistry.derive()` → `ToolScope.schemas()` | 默认隐藏工具必须被显式 expose；新增高风险工具优先默认隐藏；不得绕过 scope 把全量 schema 直接交给模型。 |
| Preflight | `ToolExecutor` | 类型/枚举/required/min/max 放 JSON Schema；安全上下文放 `required_context_keys`；权限/白名单/manifest/跨字段校验放 custom preflight。 |
| Execute | `tool.execute(context, **kwargs)` | 只做参数归一化、mode 路由、调用 service、错误映射、单项失败处理。service 不读 LLM schema，不生成 XML，不写 receipt。 |
| Render | `ToolOutputRenderer` | 普通返回值递归渲染；工具不得手写 XML 或为渲染构造私有 result layer。 |
| Output Cache | `ToolOutputCache` | 小文本内联为 `<contents>`；大文本写入 `ToolContentStore` 生成 `cnt_*`；每段 `cacheable_texts[i]` 是独立内容单元，不能提前拼接。 |
| Runtime File | `ToolRunFileStore` | 生产 `tfile_*`；按 `user_id/session_id` 校验作用域；模型和工具都不能传本地路径、OSS key 或 base64 作为跨工具文件协议。 |
| URL Cache | `WebContentCacheService` + repositories | web/document 共享的 URL 缓存边界；Redis 存 active entry 和 TTL，Mongo 存正文，Arq 刷新 stale，GC 清理 inactive。 |
| Background | GC schedulers + Arq worker | 主服务启动 `ToolRunFileStoreGcScheduler` 和 `WebContentCacheGcScheduler`；独立 worker 消费 stale refresh 队列。 |
| Suggested Actions | `SuggestedAction(s)` | 可写工具名、mode、原因、优先级和轻量 metadata；不写完整调用参数；不代替 schema 和提示词边界。 |

## 三类引用

| 引用 | 生产者 | 消费者 | 语义 |
| --- | --- | --- | --- |
| `search_ref` | `web_search`、`academic_search` | `web_fetch(mode="from_search_results")` | 搜索候选到真实 URL 的短期映射，模型不直接拿 URL。 |
| `tfile_*` | `web_fetch`、`document_parse` 直链下载等 | `document_parse(mode="from_web_fetch")` | 工具运行期临时文件引用，按 `user_id/session_id` 隔离。 |
| `cnt_*` | `ToolOutputCache` | `tool_content_read`、`tool_content_sequential_read` | 大文本缓存凭证，表示已有内容，不代表新外部抓取需求。 |

模型看到这些引用后应沿协议消费，不能猜测内部 URL、文件路径或缓存文档 ID。

## 外界信息获取链

### 标准网页信息链

```text
web_search
  -> search_ref
  -> web_fetch(mode="from_search_results")
  -> cleaned markdown
  -> cnt_*
  -> tool_content_read / tool_content_sequential_read
```

### 学术候选链

```text
academic_search
  -> search_ref
  -> web_fetch(mode="from_search_results")
  -> document_parse (when URL resolves to a file)
  -> cnt_*
  -> session read tools
```

这里要特别明确一条架构约束：

- `academic_search` 在模型可见层面是与 `web_search` 平行的工具。
- 但在实现层面，它属于 `web_search` 的定向扩展。
- 目录与编排入口上，它仍必须保持为 `web_tools/` 顶层并列工具，而不是嵌进 `web_search/` 目录。

因此 `academic_search` 与 `web_search` 之间共享缓存、runtime context、候选构建、排序和 `search_ref` 协议，不应被误判为“不够解耦”的问题。这类强耦合是有意设计，目标是让联网搜索工具族维持统一协议和统一缓存边界，而不是把它们拆成多个彼此独立、重复实现的子系统。

所以后续不要因为 `academic_search` 复用了 `web_search` 内部逻辑，就把只服务于搜索工具族的能力机械提权到更高公共层。只有当这些逻辑已经被搜索工具族之外的多个系统稳定消费时，才值得评估是否真的应该抽成公共基础层。

同时也不要因为它属于 `web_search` 的扩展，就把 `academic_search` 的编排入口重新塞回 `web_search/` 内部。工具间可以强复用，但单个工具的编排入口始终保持业务域顶层并列，这是刻意选择的目录与架构风格。

### 直达网页链

```text
web_fetch(mode="from_direct_urls")
  -> cleaned markdown
  -> cnt_*
  -> session read tools
```

### 文件直链链路

```text
document_parse(mode="from_direct_urls")
  -> httpx direct fetcher
  -> ToolRunFileStore
  -> DocumentParseService
  -> parsed markdown
  -> URL content cache + cnt_*
  -> session read tools
```

### 搜索命中文件但模型不确定资源类型时

```text
web_fetch(mode="from_search_results")
  -> non-HTML file_ref tfile_*
  -> document_parse(mode="from_web_fetch")
  -> parsed markdown
  -> URL content cache + cnt_*
```

`web_fetch` 和 `document_parse` 的强耦合是正确行为：它们共同构成核心外界信息获取工具体系。`web_fetch` 负责 HTML 抓取、未知 URL 探测和非 HTML 文件移交，`document_parse` 负责文件内容抽取；二者共享 URL 内容缓存、fetcher 和 `source_scope` metadata，保证同一 URL 的网页正文、文件占位和解析 Markdown 能走同一缓存路径。

## Web / Document 边界

- 明显的 PDF、图片、Office、表格等文件直链，直接调用 `document_parse(mode="from_direct_urls")`。
- 普通 HTML 页面或不确定类型 URL，调用 `web_fetch`。
- 多页站点采集，调用 `web_crawl`。
- `web_search` 只找候选，不能把 preview 或 supplier answer 当最终证据。
- `academic_search` 只负责论文候选发现和可选 OpenAlex 水合，不读取正文或文件。

这条边界应同时写进 `web_fetch` 和 `document_parse` 的提示词，最大限度减少明显文件直链被 `web_fetch -> tfile_* -> document_parse` 二次转发。

## URL 缓存路径

`web_content_cache` 是 web/document 共同的 URL 内容缓存边界。它不是某个 web tool 的私有目录，而是位于 `src/chat/application/tools/common/web_content_cache/` 的工具统一切面。

- HTML 成功抓取后，`web_fetch` 写入清洗后的 Markdown。
- HTML crawl 页面同样通过 `WebContentCacheService` 读写同一 URL 缓存；缓存命中时仍保留 raw HTML 用于继续抽链。
- 非 HTML 抓取后，`web_fetch` 先写占位文档，并把 `source_cache_doc_id` 写进 `tfile_*` metadata。
- `document_parse` 解析来源为 `web_fetch` 的文件后，回填同一 URL 缓存文档的 Markdown，并标记 `parser=document_parse` 和 `parser_version`。
- `document_parse(mode="from_direct_urls")` 也先读同一 URL parse 缓存；未命中时下载文件、预创建占位、解析并回填。
- stale 命中返回旧内容，同时通过 Redis refresh lock 和 Arq refresh queue 安排后台刷新。

缓存访问域由 `source_scope` 决定：`web_public` 走公共缓存，`web_custom` 走用户私有缓存。document parse 读取时不能在 public/private 间串域回退。

TTL 使用两层语义：

- `soft_expire_at`：内容不再新鲜，但仍可返回；命中后触发 stale-while-revalidate。
- `hard_expire_at`：内容硬过期；Redis entry TTL 也按这个时间设置，过期后不再使用缓存。

后台刷新分两类：

- `refresh_web_fetch_cache`：重新抓取 HTML 或刷新非 HTML 占位。
- `refresh_document_parse_cache`：重新解析已有 `tfile_*` 对应文件并回写 parsed Markdown。

只启动 API 进程时，stale refresh job 只会入队，不会被消费；必须启动 Arq worker。

### Mongo 正文清理

Redis entry 是 URL cache active 状态的权威索引，并按 `hard_expire_at` 设置 TTL 自动过期。MongoDB 中的 `wisepen_web_content_cache_values` 只保存正文文档，不依赖 Mongo TTL 自动删除。

主服务启动时会启动 `WebContentCacheGcScheduler`，定期清理 Mongo 中已经不 active 的缓存正文：

- 只扫描 `updated_at` 早于保留期的 Mongo 文档。
- 对每个候选文档，按 `user_id + canonical_url + cache_mode` 查询 Redis active entry。
- 如果 Redis entry 仍指向同一个 Mongo `doc_id`，保留。
- 如果 Redis entry 不存在，或已指向新文档，删除该 Mongo 文档。

默认扫描周期是 3 天，inactive 保留期是 7 天，单次最多处理 1000 条，可通过 `tool_settings` 调整。

## Session 内容链

当工具返回 `cnt_*` 后，模型应优先使用：

- `tool_content_read(mode="ranked_expand")`：跨一个或多个 `cnt_*` 做全局语义检索。
- `tool_content_read(mode="regex_match")`：跨一个或多个 `cnt_*` 做全局精确模式匹配。
- `tool_content_sequential_read`：按 offset 顺序读取单个 `cnt_*`。

不要因为已经拿到 `cnt_*` 又重新调用 `web_fetch`、`web_crawl` 或 `document_parse`。

## 工具族流程

### Web 工具

```text
web_search
  -> candidate repository(search_ref -> URL/source_scope)
  -> web_fetch

academic_search
  -> candidate repository(search_ref -> URL/source_scope)
  -> optional OpenAlex hydration
  -> web_fetch

web_fetch
  -> URL cache read
  -> httpx/scrapling
  -> HTML: cleaner -> URL cache -> cacheable_texts -> cnt_*
  -> non-HTML: URL cache stub -> tfile_* -> document_parse

web_crawl
  -> URL cache read per page
  -> httpx/scrapling
  -> cleaner -> URL cache -> cacheable_texts -> cnt_*
  -> raw_html link extraction for BFS
```

Web 工具的模型约束：search preview 不是证据；academic_search 水合字段不是正文；明显文件直链不绕 `web_fetch`。

### Document 工具

```text
document_parse(from_web_fetch)
  -> ToolRunFileStore.resolve_ref
  -> parsed URL cache read
  -> DocumentParseService
  -> URL cache writeback when source_kind=web_fetch
  -> cacheable_texts -> cnt_*

document_parse(from_direct_urls)
  -> parsed URL cache read
  -> direct fetcher
  -> ToolRunFileStore publish
  -> same parse path
```

Document 工具的模型约束：只解析文件，不读普通 HTML；不接本地路径、OSS key、`cnt_*`。

### Session 工具

```text
cnt_* receipt
  -> tool_content_read for cross-document retrieval
  -> tool_content_sequential_read for single-content continuation
```

Session 工具的模型约束：只消费已有内容，不抓取、不解析、不再生产 `cnt_*`。

### Skill 工具

```text
SkillMatcher
  -> allowed_skill_ids
  -> load_skill
  -> manifest
  -> load_skill_asset
```

Skill 工具的模型约束：只加载本轮允许 skill；asset path 必须来自 manifest；`create_skill` 当前注册但发布后端未接通时会失败。

### Math 工具

```text
LLM selects narrow solver
  -> MathSolveTool common wrapper
  -> specific solver service
  -> ordinary structured result
  -> recursive renderer
```

Math 工具的模型约束：不访问外部信息，不执行任意 Python，不使用 `cnt_*`/`tfile_*`。

## Tool 文档模板

每个 tool 文档至少包含：

| 章节 | 内容 |
| --- | --- |
| 实现入口和内部 service | 文件位置和职责 |
| 何时使用 / 何时禁止使用 | 触发边界和相邻工具分工 |
| 参数契约 | schema 能表达的规则，以及 execute/preflight 才能表达的校验 |
| 内部运行机制 | 调用链、fallback、缓存、排序、解析 |
| 输出结构 | 是否使用 `ToolReturn.cacheable_texts` |
| 与其它工具的协作链 | 上下游工具如何衔接 |
| 对模型的硬约束 | 不能伪造、不能绕过的规则 |
| 可插拔组件 | provider、parser、fetcher 等替换点 |
| 后续优化方向 | 提示词、缓存、测试、可观测性 |
| 相关测试 | 至少覆盖的范围 |

## 模型约束

- 不要伪造 `search_ref`、`tfile_*`、`cnt_*`、`skill_id`、asset path 或内部 URL。
- 不要把 search preview、supplier answer、hydration metadata 当作正文证据。
- 不要把 obvious file URL 包一层 `web_fetch`，直接给 `document_parse` 的 direct URL 模式。
- 不要把 `file_refs` 和 `direct_urls` 混在一次 document parse 调用里；不要把 `urls` 和 `search_refs` 混在一次 web fetch 调用里。
- 已有缓存凭证时先读缓存；只有用户明确要求刷新或现有证据不足时才重新获取。
- 不能从模型参数传入 `user_id`、`session_id`、API key、object key 或本地路径；这些只能来自可信 context 或 preflight metadata。

## 可插拔组件

| 层 | 当前组件 | 可替换实验方向 |
| --- | --- | --- |
| 搜索 provider | 4get/DDG、Exa、自定义 Exa/Tavily/AnySearch/百度千帆 | provider 扩展、custom provider 扩展、provider capability 扩展（如 academic search）。 |
| 搜索内部小模型 | candidate ranker（仅看 candidate 文本，不看 supplier answer） | 提示词调优、JSON 解析容错、候选重排模型替换。 |
| Web fetcher | `HttpxFetcher` -> `ScraplingFetcher` fallback | 新增 Playwright/browser fetcher、反爬策略、质量判断阈值实验。 |
| Web cleaner | `TrafilaturaCleaner` + Markdown renderer | cleaner 替换、正文保真度评估、表格/代码块渲染策略。 |
| URL 缓存 | `WebContentCacheService` + Redis entry repository + Mongo value repository + Arq refresh queue | TTL 策略、ETag/Last-Modified 增量刷新、raw HTML 保留策略、hydrate 结果缓存。 |
| 文档 parser | PDF strategy、Docling、Pandas、Image OCR、MarkItDown | Parser 顺序实验、OCR provider 替换、PDF 页级策略优化。 |
| 内容分块 | Markdown/plain chunking pipeline | chunk 大小、结构索引、页面/锚点抽取策略。 |
| 排序 | `RankingEngine` | 本地 embedding、cross-encoder、provider reranker、混合 BM25。 |
| Skill 发布 | `SkillPublisher` protocol | 接入真实 ai-asset publisher、冲突检查、版本管理。 |

## 后续优化方向

- 持续调优 `web_fetch` / `document_parse` 提示词中的模式边界，减少文件直链误路由。
- 给直链文件类型判断增加可配置扩展名和 MIME allowlist，辅助模型和工具双层路由。
- 继续收敛 web/document 中非 HTML 占位、parse 回填等缓存逻辑，减少业务类里重复的缓存细节。
- 评估 academic_search 的 OpenAlex 水合缓存是否值得引入。
- 为 `ToolParametersSchema` 增加可表达互斥模式的 preflight DSL，减少工具 execute 内重复校验。
- 继续按工具实际下一步收敛 `suggested_action` 与 `suggested_actions` 的使用边界。
- 给跨工具链加端到端回归用例：search->fetch->read、direct file->parse->read、fetch file->parse cache hit。
