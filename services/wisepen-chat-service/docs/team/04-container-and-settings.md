# Container 与 Settings 边界规范

> 一句话：只有带生命周期、成本高或应用级共享协调器的对象才进 container；settings 只承载真正需要运行期配置的应用和基础设施参数。

本文约束依赖注入容器、应用配置和工具局部行为常量的职责边界。

## Container 注册原则

只有满足以下原因之一，才应注册到 `src/chat/container.py`：

- 拥有需要生命周期管理的资源，例如 HTTP client、Redis、Kafka、RPC、连接池、文件加载器。
- 重复创建成本高，例如模型运行时、重型本地索引、持久缓存。
- 是应用级共享协调器，例如 `ToolRegistry`、`ToolDispatcher`、`ToolContentStore`。
- 是需要进入全局 `ToolRegistry` 的 tool 实例。

不应注册：

- 普通配置值。
- 轻量无状态 renderer/converter。
- 每请求的 plan、candidate、request model、parse result。
- 不拥有资源且不作为应用入口的 helper service。
- 小 helper 函数或纯工具类。

## HTTP Client 规则

HTTP client 必须按外部集成命名，不能使用笼统名称。

推荐：

- `paddle_ocr_http_client`
- `asset_download_http_client`
- `search_api_http_client`

避免：

- `tool_http_client`
- `common_http_client`
- `http_client_for_tools`

异步请求路径使用 `httpx.AsyncClient`。拥有连接池的 integration client 不应自行创建 HTTP client，应由 container 注入。

## Settings 与局部常量边界

`app_settings` 承载全局应用和基础设施配置：

- Redis、Mongo、Kafka、RPC、Nacos、OSS 等连接信息。
- LLM、embedding、reranker 等全局模型配置。
- 全局限制，例如 `TOOL_RESULT_MAX_CHARS`。
- 服务发现、部署、运行期配置。

工具行为已经稳定时，不再维护聚合式 `tool_settings` 门面。工具专属默认值应就近放在拥有该行为的模块中：

- 单个工具的 timeout。
- 单个工具的 retry。
- 只影响工具行为的解析阈值或策略开关。

只有确实需要部署期或运行期调整的值，才应进入 `app_settings`。不要因为某个值“看起来像配置”就把稳定行为常量集中到一个大 settings 文件。

## Nacos 规则

当前服务保持 `container` 作为唯一运行入口。

不要为了工具行为常量增加第二套 Nacos 加载路径，除非服务先完成清晰的多源配置设计。

## Review 清单

新增 provider 前必须回答：

| 问题 | 为什么问这个 |
| --- | --- |
| 这个对象拥有哪个资源 | 确认生命周期管理需求。 |
| shutdown 时是否需要关闭或 flush | 确认必须注册到 container，而不是模块级缓存。 |
| 单例避免了什么具体成本 | 确认不是为了“看起来规范”而注册。 |
| 为什么 direct constructor 或模块级 cache 不够 | 确认注册到 container 是必要选择。 |
| provider 名称是否绑定具体集成 | 避免 `common_xxx` 这类笼统命名。 |

新增 setting 前必须回答：

| 问题 | 为什么问这个 |
| --- | --- |
| 它是否真的需要运行期配置 | 确认放进 `app_settings`，还是保留为工具/组件局部常量。 |
| 是否复制了已有 setting | 避免同一配置出现两处。 |
| 是否正在形成聚合式工具 settings 门面 | 稳定工具行为值应就近内联，避免集中转发参数。 |
