# Web Search 扩展规范

> 一句话：扩展搜索体系时，优先加 provider capability 和显式工具链，不要回退到隐式路由、通用 endpoint 主链或跨族公共抽象。

本文约束后续如何扩展搜索工具体系，包括：

- 如何新增一个搜索源
- 如何让一个搜索源支持显式 `academic_search`
- 如何新增新闻搜索、图片搜索等专用搜索工具
- 禁止事项与架构红线

目标不是列一堆文件名，而是明确扩展顺序、判断标准和禁止事项，避免把当前已经收紧的结构重新做散。

## 当前结构先记住两点

### 1. `web_search` 和 `academic_search` 是两个平行工具

- `web_search` 只做普通网页候选发现。
- `academic_search` 只做显式学术候选发现。

不要把学术搜索再塞回 `web_search` 的 mode，也不要重新引入小模型隐式路由。

### 2. 学术能力来自 provider capability，不来自通用 endpoint

- provider 是否支持 academic search，由 `SearchProviderName.supports_academic_search` 决定。
- `web_search` 只走 `search_web(...)`。
- `academic_search` 只走 `search_academic(...)`。
- `academic_search/service.py` 只负责单次 academic provider 调用和 OpenAlex 水合。

后续扩展必须保持这个结构，不要再回退到“一个通用 search 接口 + endpoint 参数切换所有垂类”的老路。

## 目录结构

```
search_services/
    ranking.py                  # LLM 候选排序（search 工具族共享，非 service 专属）
    errors.py                   # 异常体系
    runtime_context.py          # 运行期配置解析
    custom_source_factory.py    # Custom 搜索源工厂
    providers/                  # Provider 定义（枚举、请求/响应模型）
    searchers/                  # Searcher 实现（DDG、Exa、Tavily 等）
    candidate_store/            # search_ref → URL 映射缓存
    services/
        search.py               # 共享搜索编排：execute_provider_search、WebSearchResult、WebSearchCustomSource
        candidates.py           # 共享候选构建：WebSearchCandidate、build_candidates、build_candidate_mappings
        web_search/
            service.py          # WebSearchService
            result_builder.py   # build_web_search_tool_return
        academic_search/
            service.py          # AcademicSearchService
            result_builder.py   # build_academic_search_tool_return
            hydrators/          # OpenAlex 水合
```

分层逻辑：

- `services/search.py`：平台/custom 异常翻译、provider 选择、search_once 委托 —— 两个 service 共用。
- `services/candidates.py`：候选对象构建与映射 —— 两个 service 共用。
- `services/web_search/` 和 `services/academic_search/`：各自的 service 编排和 result builder，互不依赖。
- `ranking.py`：放在顶层，因为它是跨 service 的 LLM 排序能力，不属于任何单个 service。
- `custom_source_factory.py`：独立于 service，由 tool 层调用构造 `WebSearchCustomSource`。

## 一、如何新增一个普通搜索源

“普通搜索源”指：可以参与 `web_search`，不一定支持 `academic_search`。

### 第一步：确认接入类型

1. **平台内置源**：只由服务端配置，用户不能上传自己的 API key。
2. **custom 源**：用户可以上传自己的 API key，运行时通过凭证切换。

不要一开始就把两条路都接上。先明确它是平台源、custom 源，还是两者都支持。

### 第二步：给 provider 枚举加新值

入口：`search_services/providers/models.py`

- 在 `SearchProviderName` 中新增 provider 枚举值。
- 默认 `supports_academic_search=False`。

只有当它真的支持显式学术搜索时，才改成 `True`。

### 第三步：新增 provider request / response 适配

目录：`search_services/providers/`

- 请求对象：把内部请求转成 HTTP 请求。
- 响应映射：把第三方返回归一化为 `ProviderSearchResponse`。

要求：

- 普通网页搜索只实现普通 web search 所需字段。
- 不要为了“以后可能支持学术”提前塞一堆学术特化字段。
- `ProviderSearchResponse` 只返回统一候选结果，不带工具层逻辑。

### 第四步：新增 searcher

目录：`search_services/searchers/`

- 实现 `search_web(...)`。
- 如果暂时不支持学术搜索，就不要实现 `search_academic(...)`，沿用基类默认报错即可。

### 第五步：接入 DI 容器

入口：`src/chat/container.py`

平台源需要：

- 在 `_build_platform_web_searchers()` 里加入 provider 实例。
- 如果需要配置项，补 `app_settings.py`。

custom 源需要：

- 在 `WebSearchCustomSourceFactory._provider_searcher()` 里加分支。
- 在 `WebSearchCustomSourceFactory._base_url()` 里加 base_url 分支。
- 如需配置项，补 `app_settings.py`。

### 第六步：确认凭证侧是否允许这个 provider

- 如果支持 custom：`createWebSearchCredential` 的请求模型通常不需要单独改，只要 `SearchProviderName` 枚举已有新值即可。
- 如果只支持平台源：不要把它误接到 custom 凭证上传链路。

### 第七步：补文档和测试

至少同步：

- `docs/tools/web/web_search.md`
- `docs/tools/toolchain_architecture.md`
- provider 接入回归测试
- `web_search` 正常调用测试

## 二、如何让一个搜索源支持显式 academic_search

前提：这个 provider 已经存在，且它真的提供稳定的学术搜索能力。

不要因为它“能搜到论文链接”就算支持 academic search。只有当它对论文/文献检索有明确能力边界时，才接入显式学术搜索。

### 第一步：打开 provider capability

入口：`search_services/providers/models.py`

- 让对应 `SearchProviderName.supports_academic_search` 返回 `True`。

这是整个学术能力暴露链的总开关。

### 第二步：实现 `search_academic(...)`

在对应 provider 的 searcher 中实现。

要求：

- `search_web(...)` 和 `search_academic(...)` 必须是两条显式路径。
- 不要再引入一个通用 endpoint 参数去做二次路由。
- `search_academic(...)` 只负责 provider 原生学术搜索能力，不负责 OpenAlex 水合。

如果 provider 本身支持通过某个 query/category 参数切到学术搜索，可以在它自己的 searcher / request 对象内部处理；但这层开关只留在该 provider 内部，不上提回通用主链。

### 第三步：确认 custom / platform 哪条链要支持 academic

当前 `academic_search` 的工具暴露依赖：

- 运行时 `search_config.supports_academic`。
- `supports_academic` 来自当前激活搜索凭证上的 `support_academic`。
- `support_academic` 由搜索源能力决定，而不是由通用 endpoint 路由决定；当前只有 Exa 会置为 `true`。

如果这是 custom provider：

- `MongoWebSearchCredentialRepository.upsert_custom_credential()` 会按 `provider.supports_academic_search` 自动写入 `support_academic`。
- 只要 provider capability 打开，custom 凭证链路会自动跟上。

如果未来要让平台源也支持 academic：

- 需要单独评估 `WebSearchRuntimeContextResolver` 和 tool 暴露策略。
- 目前默认 academic 还是走 custom 搜索源。

### 第四步：不要碰 OpenAlex 判断边界

- provider 是否支持 academic search，决定 `academic_search` 能不能暴露。
- OpenAlex key 只决定学术结果是否做可选水合。

不要把这两层重新耦回去。

### 第五步：确认 `academic_search` 工具文档

至少更新 `docs/tools/web/academic_search.md`。

如果学术 provider 不再只有 Exa，一定要把文档从“当前实际支持的搜索源是 Exa”改成新的事实。

## 三、哪些地方不要改错

### 1. 不要重新引入通用 endpoint 主链

不要再做回这种结构：

- `service.search(... endpoint=...)`
- `tool.execute(... mode=web/news/scholar)`

当前已经明确收紧为：

- `search_web(...)`
- `search_academic(...)`

### 2. 不要把工具族内部实现机械提权到公共层

如果某个能力只服务搜索工具族（搜索候选构建、search_ref 映射、搜索排序拼装），就继续留在 `search_services/` 内部，不要因为新增 provider 就顺手抽成更高公共层。

### 3. 不要把 `academic_search` 塞回 `web_search/` 目录里

即使一个 provider 新增了学术能力，也只是在实现层面扩展搜索工具族。目录与编排入口仍要保持：

- `web_search_tool.py`
- `academic_search_tool.py`

在 `web_tools/` 顶层并列。

### 4. 不要把 OpenAlex 变成 academic_search 暴露条件

OpenAlex 永远只是可选水合层，不参与工具是否暴露的判断。

### 5. 不要重新引入多跳逻辑

当前搜索是单次调用 + fallback（主查询空结果时执行一次备选查询）。不要再引入 hop 计数、coverage check、next query rewrite 等多跳机制。

## 四、如何新增新闻搜索、图片搜索等专用搜索工具

当前已有 `web_search` 和 `academic_search` 两个平行工具。后续如果需要开新闻搜索、图片搜索等专用工具，遵循与 `academic_search` 相同的扩展模式。

### 核心原则：专用搜索 = 新工具 + searcher 占位方法 + capability 开关

不要用 mode/endpoint 参数在现有工具内部做二次路由。每开一个专用搜索类型，就是：

1. 一个新的顶层工具（如 `news_search_tool.py`）。
2. 对应的 service 和 result builder（在 `search_services/services/news_search/` 下）。
3. searcher 基类上新增一个占位方法（如 `search_news(...)`）。
4. provider 枚举上新增 capability 开关（如 `supports_news_search`）。

### 第一步：在 searcher 基类上新增占位方法

入口：`search_services/searchers/base.py`

新增一个默认 `raise NotImplementedError` 的占位方法：

```python
async def search_news(self, *, query: str, max_results: int = 10) -> ProviderSearchResponse:
    raise NotImplementedError(f"{self.__class__.__name__} does not support news search")
```

与 `search_academic(...)` 完全对齐：不支持该搜索类型的 provider 沿用基类默认报错，支持的 provider 覆写此方法。

同理，图片搜索就是 `search_images(...)`，视频搜索就是 `search_video(...)`，依此类推。

### 第二步：在 provider 枚举上新增 capability

入口：`search_services/providers/models.py`

在 `SearchProviderName` 上新增 property，如：

```python
@property
def supports_news_search(self) -> bool:
    return self in _NEWS_CAPABLE_PROVIDERS
```

这是新工具暴露链的总开关，与 `supports_academic_search` 角色完全一致。

### 第三步：新增 service 和 result builder

目录：`search_services/services/news_search/`

```
services/news_search/
    service.py          # NewsSearchService
    result_builder.py   # build_news_search_tool_return
```

service 复用 `services/search.py` 中的 `execute_provider_search`（只需改 `search_once` lambda 调用 `searcher.search_news(...)`）和 `services/candidates.py` 中的候选构建逻辑。

result builder 根据专用搜索类型定义自己的可见字段（如新闻搜索可能暴露 `published_date`、`source_name`，图片搜索可能暴露 `thumbnail_url`、`image_dimensions`）。

### 第四步：新增顶层工具

入口：`web_tools/news_search_tool.py`

与 `academic_search_tool.py` 完全平行：

- 默认隐藏（`expose_by_default=False`）。
- `ChatTurnCoordinator` 按 capability 和凭证决定是否暴露。
- 内部流程：query → service → candidate build → ranking → search_ref mapping。
- 复用 `_search_tool_utils.py` 中的 `search_with_fallback`、`select_recommended_ids`、`store_candidate_mappings`。

### 第五步：接入容器

在 `container.py` 中：

- 构造 `NewsSearchService`（注入 platform searchers）。
- 构造 `NewsSearchTool`（注入 service + candidate repository + custom source factory）。

### 第六步：更新 custom source factory

如果该搜索类型支持 custom 凭证：

- `WebSearchCustomSourceFactory` 无需改动，因为它构造的是通用 `WebSearchCustomSource`（包含 provider + searcher + api_key），searcher 上已有 `search_news(...)` 占位方法。

如果需要专属配置（如不同的 base_url），在 factory 中按 provider 分支处理。

### 扩展顺序总结

1. searcher 基类新增 `search_xxx(...)` 占位方法。
2. `SearchProviderName` 新增 `supports_xxx_search` capability。
3. 新增 `search_services/services/xxx_search/`（service + result builder）。
4. 新增 `web_tools/xxx_search_tool.py` 顶层工具。
5. 接入容器，确认暴露条件。
6. 补文档和测试。

## 五、推荐扩展顺序

### 新增普通搜索源

1. 加 `SearchProviderName`。
2. 新增 provider request / mapper。
3. 新增 searcher，先只实现 `search_web(...)`。
4. 接入 container 或 custom source factory。
5. 补文档和测试。

### 让现有搜索源支持 academic

1. 打开 `supports_academic_search`。
2. 在对应 searcher 实现 `search_academic(...)`。
3. 确认凭证 `support_academic` 自动链路。
4. 更新 `academic_search` 文档和回归测试。

## 六、当前主要代码入口

| 关注点 | 入口 |
| --- | --- |
| Provider 枚举与能力 | `search_services/providers/models.py` |
| Provider 适配 | `search_services/providers/` |
| Searcher 实现 | `search_services/searchers/` |
| 共享搜索编排 | `search_services/services/search.py` |
| 共享候选构建 | `search_services/services/candidates.py` |
| Web search service | `search_services/services/web_search/service.py` |
| Web search result builder | `search_services/services/web_search/result_builder.py` |
| Academic search service | `search_services/services/academic_search/service.py` |
| Academic search result builder | `search_services/services/academic_search/result_builder.py` |
| OpenAlex 水合 | `search_services/services/academic_search/hydrators/` |
| LLM 候选排序 | `search_services/ranking.py` |
| Custom 搜索源工厂 | `search_services/custom_source_factory.py` |
| 运行期配置解析 | `search_services/runtime_context.py` |
| 异常体系 | `search_services/errors.py` |
| search_ref 映射缓存 | `search_services/candidate_store/` |
| 普通搜索工具 | `web_tools/web_search_tool.py` |
| 学术搜索工具 | `web_tools/academic_search_tool.py` |
| 搜索公共工具函数 | `web_tools/_search_tool_utils.py` |
| 凭证仓储 | `core/persistence/mongo/web_search_credential_repository.py` |
| 容器接线 | `src/chat/container.py` |

## 七、当前普通搜索源接入状态

- 平台默认：4get/DDG。
- 平台可选：Exa，受平台 Exa 开关和平台 key 控制。
- Custom：Exa、Tavily、AnySearch、百度千帆。

百度千帆当前只作为普通网页搜索源接入 `web_search`，请求百度千帆 AI 搜索 `POST /v2/ai_search/web_search`，响应只映射 `references` 中的 web 候选。它不打开 `supports_academic_search`，也不影响 `academic_search` 的 Exa/OpenAlex 边界。

## 八、一句话原则

后续扩展搜索工具时，优先扩展 provider capability 和显式工具链，不要重新长回隐式路由、多垂类 endpoint 主链和跨工具族的错误公共抽象。
