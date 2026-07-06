# web_search

> 一句话：`web_search` 只负责发现普通网页候选，不读正文、不解析文件、不做多跳搜索。

实现入口：`src/chat/application/tools/web_tools/web_search_tool.py`

`web_search` 只做显式单次网页候选发现。它不再做意图路由，不再做内部多跳搜索，不再自动生成下一跳 query。工具内部只保留候选选择小模型。

## 何时使用

- 用户需要一般网页候选，而不是论文候选。
- 需要先拿到网页候选；若摘要不足以回答，再交给 `web_fetch` 抓正文。
- 需要实时、外部、可验证来源的信息。

## 不适合做什么

- 不适合论文/文献检索。此类需求使用 `academic_search`。
- 不适合直接读取正文、PDF 或 Office 文件。
- 不适合在摘要不足、需要强证据或细节核验时把 preview 当最终证据。

## 输入

| 参数 | 类型 | 规则 |
| --- | --- | --- |
| `question` | `string` | 用户原始问题。 |
| `query` | `string` | 本次执行的网页搜索 query；若无结果，由模型重写后再次调用。 |
| `max_results` | `integer` | 可选，默认 10，最大 20。 |

## 内部流程

```text
question
  -> query
  -> provider web search
  -> candidate build
  -> candidate selection (title/url/overview/highlights only)
  -> search_ref mapping
```

约束：

- 工具只执行一次显式 query，不内置 fallback query。
- 查询为空结果时直接失败，由模型按任务目标重写 query 后重新调用。
- 工具不会做 coverage retry、hop merge 或 next query rewrite。

## 搜索源

当前搜索源分为三类：

- `platform_default`：平台默认源，对外只暴露一个稳定标识；内部使用 4get，并在失败或空结果时降级到 DDGS。
- `platform_member`：会员平台源，会员身份本身不绑定具体 provider；运行期按平台配置路由到 Exa、Tavily 等可复用 integration，并使用平台密钥。
- `custom`：用户自定义源，使用用户上传的 API key，当前支持 Exa、Tavily、AnySearch、百度千帆 AI 搜索。

`platform_member` 和 `custom` 可以复用同一个 provider searcher adapter，但 source class、密钥归属、错误语义和缓存域必须分开。

百度千帆接入的是普通网页搜索源：请求 `POST /v2/ai_search/web_search`，从响应 `references` 中只映射 web 候选，不支持 `academic_search`。

## 输出

返回 `ToolReturn(tag="web_search_result")`，不缓存正文内容。

可见结果包含：

- `query`
- `candidates`
- `recommended_ids`
- `supplier_answers`
- `suggested_action`

候选对模型只暴露：

- `search_ref`
- `title`
- `overview`
- `highlights`

真实 URL 仍保存在候选映射缓存里；需要正文、强证据或细节核验时，由 `web_fetch(search_refs=[...])` 解析。

## search_ref 协议

`search_ref` 是 `web_search` 的核心产物。

- `web_search` 负责发现候选并写入 `search_ref -> url`。
- `web_fetch` 负责消费 `search_ref` 抓取正文。
- 模型不应伪造 `search_ref`。

## Suggested Actions

当前建议：

- `web_fetch(search_refs=[...])`

补充约束：

- `supplier_answers` 和候选摘要仍可暴露给模型作为检索提示；若摘要已经足以回答用户问题，可以不继续调用 `web_fetch`。
- 候选选择小模型不再读取 `supplier_answers`，只看候选自身字段。
- 候选选择小模型每次输出 1 到 5 个候选编号，宁缺勿滥，不强制凑满 5 个。

不再暴露任何 hydrate 工具建议。

## 相关文件

| 关注点 | 入口 |
| --- | --- |
| 工具实现 | `web_tools/web_search_tool.py` |
| Web search service | `search_services/web_search.py` |
| Web search result builder | `search_services/result_builders/web.py` |
| 共享搜索编排 | `search_services/pipeline/search_executor.py` |
| 共享候选构建 | `search_services/pipeline/candidates_builder.py` |
| LLM 候选选择 | `search_services/pipeline/candidate_selector.py` |
| 搜索源工厂 | `search_services/factories/` |
| 运行期配置解析 | `search_services/core/runtime_context.py` |
| search_ref 映射缓存 | `search_services/candidate_store/` |
| 搜索公共工具函数 | `web_tools/_search_tool_utils.py` |
| web_fetch 工具 | `web_tools/web_fetch_tool.py` |
