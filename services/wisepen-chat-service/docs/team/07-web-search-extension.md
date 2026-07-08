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
  provider_search_tool.py
  web_search/
    service.py
    result_builder.py
    tool_utils.py
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
4. 在 `IntegrationSearcherFactory` 中注册 provider 到 searcher 的映射。
5. 如果支持学术检索，让 `SearchProviderName.supports_academic_mode` 返回 `True`，并实现 `search_academic(...)`。
6. 在 `search_tools/` 顶层新增 `xxx_search_tool.py`，继承 `ProviderSearchTool`。
7. 在 `container.py` 注册工具 provider，并加入 `tool_providers`。
8. 更新 `docs/tools/web/web_search.md` 和对应测试。

## 关键边界

- 不再新增独立 `academic_search` 工具。
- 不再引入 OpenAlex 水合链路。
- `platform_search` 只走平台默认/会员源解析，不读取 custom credential。
- provider 工具只按自身 provider 读取用户 API key，不使用“当前激活搜索配置”做路由。
- 搜索候选直接暴露 URL，由 `web_fetch(urls=[...])` 消费。
- 搜索工具默认隐藏，由 `ChatTurnCoordinator` 按 `WebSearchCredential.is_active` 动态解禁；新增 provider 工具时必须补充 active custom provider 到工具名的映射。

## 百度千帆

百度千帆当前只作为普通网页搜索源接入 `baidu_qianfan_search`，请求百度千帆 AI 搜索 `POST /v2/ai_search/web_search`，响应只映射 `references` 中的 web 候选，不打开 academic mode。
