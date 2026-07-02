# web_search

> 一句话：`web_search` 只负责发现普通网页候选，不读正文、不解析文件、不做多跳搜索。

实现入口：`src/chat/application/tools/web_tools/web_search_tool.py`

`web_search` 只做显式单次网页候选发现。它不再做意图路由，不再做内部多跳搜索，不再自动生成下一跳 query。工具内部只保留候选排序小模型。

## 何时使用

- 用户需要一般网页候选，而不是论文候选。
- 需要先拿到 `search_ref`，再交给 `web_fetch` 抓正文。
- 需要实时、外部、可验证来源的信息。

## 不适合做什么

- 不适合论文/文献检索。此类需求使用 `academic_search`。
- 不适合直接读取正文、PDF 或 Office 文件。
- 不适合把 preview 当最终证据。

## 输入

| 参数 | 类型 | 规则 |
| --- | --- | --- |
| `question` | `string` | 用户原始问题。 |
| `first_query` | `string` | 首次执行的网页搜索 query。 |
| `fallback_query` | `string` | 仅当 `first_query` 返回空结果时执行一次。 |
| `max_results` | `integer` | 可选，默认 10，最大 20。 |

## 内部流程

```text
question
  -> first_query
  -> provider web search
  -> if empty: fallback_query once
  -> candidate build
  -> candidate ranking (title/url/overview/highlights only)
  -> search_ref mapping
```

约束：

- `fallback_query` 只在首跳空结果时触发一次。
- 第二次仍为空时直接失败。
- 工具不会做 coverage retry、hop merge 或 next query rewrite。

## 搜索源

当前平台默认源仍是 4get/DDG，平台 Exa 只在平台配置打开时参与分流。用户自定义搜索凭证支持 Exa、Tavily、AnySearch、百度千帆 AI 搜索。

百度千帆接入的是普通网页搜索源：请求 `POST /v2/ai_search/web_search`，从响应 `references` 中只映射 web 候选，不支持 `academic_search`。

## 输出

返回 `ToolReturn(tag="web_search_result")`，不缓存正文内容。

可见结果包含：

- `query`
- `final_query`（仅当 fallback 查询与原始查询不同时展示）
- `candidates`
- `recommended_ids`
- `supplier_answers`
- `suggested_action`

候选对模型只暴露：

- `search_ref`
- `title`
- `overview`
- `highlights`

真实 URL 仍保存在候选映射缓存里，由 `web_fetch(mode="from_search_results")` 解析。

## search_ref 协议

`search_ref` 是 `web_search` 的核心产物。

- `web_search` 负责发现候选并写入 `search_ref -> url`。
- `web_fetch` 负责消费 `search_ref` 抓取正文。
- 模型不应伪造 `search_ref`。

## Suggested Actions

当前只建议：

- `web_fetch(mode="from_search_results")`

补充约束：

- `supplier_answers` 仍可暴露给模型作为检索提示。
- 候选排序小模型不再读取 `supplier_answers`，只看候选自身字段。

不再暴露任何 hydrate 工具建议。

## 相关文件

| 关注点 | 入口 |
| --- | --- |
| 工具实现 | `web_tools/web_search_tool.py` |
| Web search service | `search_services/services/web_search/service.py` |
| Web search result builder | `search_services/services/web_search/result_builder.py` |
| 共享搜索编排 | `search_services/services/search.py` |
| 共享候选构建 | `search_services/services/candidates.py` |
| LLM 候选排序 | `search_services/ranking.py` |
| Custom 搜索源工厂 | `search_services/custom_source_factory.py` |
| 运行期配置解析 | `search_services/runtime_context.py` |
| search_ref 映射缓存 | `search_services/candidate_store/` |
| 搜索公共工具函数 | `web_tools/_search_tool_utils.py` |
| web_fetch 工具 | `web_tools/web_fetch_tool.py` |
