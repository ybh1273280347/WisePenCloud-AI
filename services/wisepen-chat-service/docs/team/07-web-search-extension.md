# Web Search Extension

> 当前搜索工具族按 provider 拆分工具；学术检索是 provider 工具的显式 mode，不再是独立工具。

## 当前结构

```text
src/chat/application/tools/search_tools/
  platform_search_tool.py
  exa_search_tool.py
  tavily_search_tool.py
  anysearch_search_tool.py
  baidu_qianfan_search_tool.py
  base_search_tool.py
  web_search/
    search_pipeline.py
    result_builder.py
    core/
    factories/
    providers/
    searchers/
    pipeline/
```

`web_tools/` 只保留 fetch/crawl：

```text
src/chat/application/tools/web_tools/
  web_fetch_tool.py
  web_crawl_tool.py
  fetch_services/
```

## 扩展一个 provider search 工具

1. 在 `SearchProviderName` 增加 provider 枚举。
2. 在 `providers/` 中实现 request 和 response mapper。
3. 在 `searchers/integrations/` 中实现 provider searcher。
4. 在 `SearchSourceFactory` 中注册 provider 到 searcher 的映射。
5. 在 `SearchProviderName.capability` 声明 `SearchCapability(web=True, academic=...)`；支持原生学术检索时覆写 `search_academic(...)`，否则基类自动回退 `search_web(...)`。
6. 在 `search_tools/` 顶层新增 `xxx_search_tool.py`，继承唯一的 `BaseSearchTool`。
7. 在 `container.py` 注册工具 provider，并加入 `tool_providers`。
8. 更新 `docs/tools/web/web_search.md` 和对应测试。

## 关键边界

- 不再新增独立 `academic_search` 工具。
- 不再引入 OpenAlex 水合链路。
- `platform_search` 固定使用平台默认源，不读取用户 ToolConfig。
- provider 工具只声明自身 provider，并从统一 ToolConfig 接收自己的 API key。
- 平台默认搜索源声明 `SearchCapability(web=True, academic=False)`；收到 academic mode 时宽容回退 web，不视为原生支持学术检索。
- 所有搜索工具共享 `query/mode/max_results` schema，不按 academic 参数是否存在做额外能力查表。
- 搜索候选直接暴露 URL，由 `web_fetch(urls=[...])` 消费。
- custom 搜索工具声明统一 `ToolConfigSpec`，至少包含 secret `api_key`；无需在 `ChatTurnCoordinator` 维护动态暴露映射。

## 百度千帆

百度千帆当前只作为普通网页搜索源接入 `baidu_qianfan_search`，请求百度千帆 AI 搜索 `POST /v2/ai_search/web_search`，响应只映射 `references` 中的 web 候选，不打开 academic mode。
