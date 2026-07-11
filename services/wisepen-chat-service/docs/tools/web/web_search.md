# search tools

> 一句话：搜索工具族按供应商拆成多个显式工具；每次调用只执行一个 query，返回带 URL 的候选，不抓正文。

实现入口：

- `src/chat/application/tools/search_tools/platform_search_tool.py`
- `src/chat/application/tools/search_tools/exa_search_tool.py`
- `src/chat/application/tools/search_tools/tavily_search_tool.py`
- `src/chat/application/tools/search_tools/anysearch_search_tool.py`
- `src/chat/application/tools/search_tools/baidu_qianfan_search_tool.py`

共享实现入口：`src/chat/application/tools/search_tools/web_search/`

## 当前工具

| 工具 | 搜索源 | 说明 |
| --- | --- | --- |
| `platform_search` | 平台默认源或平台会员源 | 通用默认搜索工具；平台会员源按配置路由到 provider。 |
| `exa_search` | 用户 Exa API key | 支持 `mode=web` 和 `mode=academic`。 |
| `tavily_search` | 用户 Tavily API key | 原生 web；academic mode 回退 web。 |
| `anysearch_search` | 用户 AnySearch API key | 原生 web；academic mode 回退 web。 |
| `baidu_qianfan_search` | 用户百度千帆 API key | 原生 web；academic mode 回退 web。 |

不再存在独立 `web_search` 或 `academic_search` 工具。学术检索是支持该能力的 provider 工具上的显式 `mode=academic`。

搜索工具默认隐藏，每轮只按当前用户 `WebSearchCredential.is_active` 动态解禁一个入口：

- active 平台凭证（`platform_default` 或 `platform_member`）：暴露 `platform_search`。
- active custom 凭证：只暴露该 provider 对应的搜索工具。
- 没有 active 搜索凭证：不暴露搜索工具。

## 输入

所有搜索工具共享基础输入：

| 参数 | 类型 | 规则 |
| --- | --- | --- |
| `query` | `string` | 本次执行的搜索 query；无结果时由模型改写后再次调用。 |
| `max_results` | `integer` | 可选，默认 10，最大 20。 |
| `mode` | `web \| academic` | 所有搜索工具统一暴露；不支持原生 academic 的 source 自动回退 web。 |

## 内部流程

```text
query
  -> fixed source/provider
  -> SearchPipeline.search(mode)
  -> candidate build
  -> candidate selection
  -> visible candidates with urls
  -> ToolReturn(tag="<tool_name>_result")
```

约束：

- 工具只执行一次显式 query，不内置 fallback query。
- provider 工具不读取“当前激活搜索配置”，而是按自己的 provider 读取用户 API key。
- `platform_search` 只解析平台默认/会员源，不会被 custom credential 路由劫持。
- 平台默认源的能力是 `web=True, academic=False`；academic mode 会回退 web，能力声明仍保持不支持原生学术检索。
- OpenAlex 水合链路已删除；工具输出只来自 provider 原生搜索结果。

## 输出

可见结果包含：

- `query`
- `mode`
- `candidates`
- `recommended_ids`
- `supplier_answers`

候选只暴露：

- `url`
- `title`
- `overview`
- `highlights`

需要正文、强证据或细节核验时，直接调用 `web_fetch(urls=[...])`。

## 相关文件

| 关注点 | 入口 |
| --- | --- |
| 工具门面 | `search_tools/*_search_tool.py` |
| 搜索完整管线 | `search_tools/web_search/search_pipeline.py` |
| 搜索 result builder | `search_tools/web_search/result_builder.py` |
| 搜索执行管线 | `search_tools/web_search/pipeline/search_executor.py` |
| 候选构建 | `search_tools/web_search/pipeline/candidates_builder.py` |
| 候选选择 | `search_tools/web_search/pipeline/candidate_selector.py` |
| 搜索源统一工厂 | `search_tools/web_search/factories/search_source_factory.py` |
| Provider adapter | `search_tools/web_search/searchers/` |
| Provider payload/mapper | `search_tools/web_search/providers/` |
| 运行期平台源解析 | `search_tools/web_search/runtime_context_resolver.py` |
