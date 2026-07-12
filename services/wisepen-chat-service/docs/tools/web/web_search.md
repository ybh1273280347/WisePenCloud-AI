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
| `platform_search` | 平台默认源 | 无需用户配置的通用默认搜索工具。 |
| `exa_search` | 用户 Exa API key | 支持 `mode=web` 和 `mode=academic`。 |
| `tavily_search` | 用户 Tavily API key | 原生 web；academic mode 回退 web。 |
| `anysearch_search` | 用户 AnySearch API key | 原生 web；academic mode 回退 web。 |
| `baidu_qianfan_search` | 用户百度千帆 API key | 原生 web；academic mode 回退 web。 |

不再存在独立 `web_search` 或 `academic_search` 工具。学术检索是支持该能力的 provider 工具上的显式 `mode=academic`。

搜索工具使用统一 ToolConfig 配置与可见性链路：

- `platform_search` 无需用户配置，默认可见并固定使用平台默认源。
- custom provider 工具声明 `config_spec.api_key`，用户通过 `/chat/tool` 接口维护配置。
- custom provider 配置完整且启用时工具可见；缺少 API key、配置禁用或配置不存在时隐藏。
- API key 由 `ToolExecutor` 通过可信 `config` 参数注入，不进入模型参数 schema。

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
- provider 工具只读取统一 ToolConfig 注入的 `api_key`，不访问独立搜索凭据仓储。
- `platform_search` 固定使用平台默认源，不读取用户 ToolConfig。
- 平台默认源的能力是 `web=True, academic=False`；academic mode 会回退 web，能力声明仍保持不支持原生学术检索。
- 候选选择小模型只优化 `recommended_ids`；调用失败时按 provider 原始顺序推荐，不能阻断搜索结果。
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
