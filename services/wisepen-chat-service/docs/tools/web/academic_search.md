# academic_search

实现入口：`src/chat/application/tools/web_tools/academic_search_tool.py`

`academic_search` 是显式论文候选发现工具。它独立于 `web_search`，默认隐藏，只有当前用户存在激活且支持学术搜索的自定义搜索凭证时才向模型暴露。当前实际支持的搜索源是 Exa。

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
- 不适合把 Exa snippet 或 OpenAlex 水合字段当最终证据。

## 输入

| 参数 | 类型 | 规则 |
| --- | --- | --- |
| `question` | `string` | 用户原始学术需求。 |
| `first_query` | `string` | 首次执行的学术搜索 query。 |
| `fallback_query` | `string` | 仅当 `first_query` 返回空结果时执行一次。 |
| `max_results` | `integer` | 可选，默认 10，最大 20。 |

## 暴露条件

- `ToolPolicy.expose_by_default=False`
- `ChatTurnCoordinator` 仅在 `search_config.supports_academic=True` 时把它加入 `expose_tool_name_set`
- `supports_academic` 来自当前激活搜索凭证上的 `support_academic`
- `support_academic` 由搜索源能力决定，而不是由通用 endpoint 路由决定；当前只有 Exa 会置为 `true`

## 内部流程

```text
question
  -> first_query
  -> academic_search service
  -> provider academic search
  -> if empty: fallback_query once
  -> candidate build
  -> optional OpenAlex hydration
  -> final url selection
  -> candidate ranking (title/url/overview/highlights only)
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
- `open_access`

其中 `open_access` 只保留：

- `is_oa`
- `oa_status`
- `oa_url`

不返回 OpenAlex 原始对象，不返回 `display_name`，标题始终以 Exa 结果为准。

水合实现边界：

- OpenAlex 逻辑位于 `search_services/services/academic_search/hydrators/`
- 学术搜索的单次 provider 调用和 OpenAlex 水合编排位于 `search_services/services/academic_search/service.py`
- `url` 路径优先，命中失败后才回退到 `title`
- `title` 路径只接受标准化后精确匹配且唯一的结果
- URL 或 title 出现多结果时直接放弃水合，回退 Exa 结果

## URL 选择与缓存

- 默认使用 Exa 返回的 URL
- 若 OpenAlex 水合成功且 `open_access.oa_url` 可用，则返回该 URL
- 最终 URL 会写入现有 `search_ref -> url` 映射缓存
- 后续 `web_fetch(mode="from_search_results")` 可直接消费该 `search_ref`

## 输出

返回 `ToolReturn(tag="academic_search_result")`，不缓存正文内容。

每个候选对模型可见：

- `search_ref`
- `title`
- `url`
- `final_url_source`
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
| Academic search service | `search_services/services/academic_search/service.py` |
| Academic search result builder | `search_services/services/academic_search/result_builder.py` |
| OpenAlex 水合 | `search_services/services/academic_search/hydrators/` |
| 共享搜索编排 | `search_services/services/search.py` |
| 共享候选构建 | `search_services/services/candidates.py` |
| LLM 候选排序 | `search_services/ranking.py` |
| Custom 搜索源工厂 | `search_services/custom_source_factory.py` |
| 运行期配置解析 | `search_services/runtime_context.py` |
| search_ref 映射缓存 | `search_services/candidate_store/` |
| 搜索公共工具函数 | `web_tools/_search_tool_utils.py` |
