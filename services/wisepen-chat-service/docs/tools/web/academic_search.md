# academic_search

> 一句话：`academic_search` 是显式论文候选发现工具，默认隐藏，只有当前运行时搜索源支持学术搜索时才暴露。

实现入口：`src/chat/application/tools/web_tools/academic_search_tool.py`

`academic_search` 是显式论文候选发现工具。它独立于 `web_search`，默认隐藏，只有当前运行时搜索源支持显式 academic search 时才向模型暴露。当前实际支持 academic capability 的 provider 是 Exa，但它既可以由 `custom` 源使用用户密钥调用，也可以由 `platform_member` 源使用平台密钥调用。

## 架构定位

`academic_search` 在模型可见层面是与 `web_search` 平行的显式工具，不是 `web_search` 的内部 mode。

但在实现层面，它复用 `search_services/` 的共享能力（搜索编排、候选构建、search_ref 映射、runtime context），属于搜索工具族的定向扩展，而不是一个完全独立的联网搜索子系统。

这里的强复用是有意为之。后续不要因为看到 `academic_search` 复用了 `search_services/` 内部实现，就把只服务搜索工具族的逻辑机械提权到更高公共层。只有当某段能力已经被多个非 web-search 家族稳定共享时，才值得重新评估是否上提。

## 何时使用

- 用户明确要论文、文献、引用、研究证据、会议或期刊候选。
- 需要先拿到论文候选，再决定是否抓正文或 PDF。

## 不适合做什么

- 不适合一般网页搜索或新闻搜索。
- 不适合直接读取论文正文。
- 不适合把 provider snippet 或 OpenAlex 水合字段当最终证据。

## 输入

| 参数 | 类型 | 规则 |
| --- | --- | --- |
| `question` | `string` | 用户原始学术需求。 |
| `query` | `string` | 本次执行的学术搜索 query；若无结果，由模型重写后再次调用。 |
| `max_results` | `integer` | 可选，默认 10，最大 20。 |

## 暴露条件

- `ToolPolicy.expose_by_default=False`
- `ChatTurnCoordinator` 仅在 `search_config.supports_academic=True` 时把它加入 `expose_tool_name_set`
- `supports_academic` 来自运行时解析出的搜索源 capability
- capability 由 provider 原生能力决定，而不是由通用 endpoint 路由决定；当前 Exa 会置为 `true`

## 内部流程

```text
question
  -> query
  -> academic_search service
  -> provider academic search
  -> candidate build
  -> optional OpenAlex hydration
  -> search_ref URL selection
  -> candidate selection (title/url/overview/highlights only)
  -> search_ref mapping
```

## OpenAlex 水合边界

OpenAlex 只作为可选水合来源，不参与工具暴露判断。

水合后模型可见字段只保留：

- `doi`
- `publication_year`
- `cited_by_count`
- `authors`
- `institutions`

不返回 OpenAlex 原始对象，不返回 `display_name`，标题始终以搜索源结果为准。

水合实现边界：

- OpenAlex 逻辑位于 `search_services/hydrators/academic/`
- 学术搜索的单次 provider 调用和 OpenAlex 水合编排位于 `search_services/academic_search.py`
- `url` 路径优先，命中失败后才回退到 `title`
- `title` 路径只接受标准化后精确匹配且唯一的结果
- URL 或 title 出现多结果时直接放弃水合，回退搜索源结果

## URL 选择与缓存

- 始终使用搜索源返回的 URL 作为抓取 URL
- OpenAlex 水合只补充 DOI、年份、引用数、作者和机构，不覆盖 `search_ref -> url`
- 搜索源 URL 会写入现有 `search_ref -> url` 映射缓存
- 后续 `web_fetch(search_refs=[...])` 可直接消费该 `search_ref`
- URL 不直接暴露给模型，模型只能通过 `search_ref` 交给 `web_fetch`

## 输出

返回 `ToolReturn(tag="academic_search_result")`，不缓存正文内容。

每个候选对模型可见：

- `search_ref`
- `title`
- `overview`
- `highlights`
- 允许暴露的 OpenAlex 水合字段

可见结果还包含：

- `recommended_ids`
- `suggested_action`

## 相关文件

| 关注点 | 入口 |
| --- | --- |
| 工具实现 | `web_tools/academic_search_tool.py` |
| Academic search service | `search_services/academic_search.py` |
| Academic search result builder | `search_services/result_builders/academic.py` |
| OpenAlex 水合 | `search_services/hydrators/academic/` |
| 共享搜索编排 | `search_services/pipeline/search_executor.py` |
| 共享候选构建 | `search_services/pipeline/candidates_builder.py` |
| LLM 候选选择 | `search_services/pipeline/candidate_selector.py` |
| 搜索源工厂 | `search_services/factories/` |
| 运行期配置解析 | `search_services/core/runtime_context.py` |
| search_ref 映射缓存 | `search_services/candidate_store/` |
| 搜索公共工具函数 | `web_tools/_search_tool_utils.py` |
