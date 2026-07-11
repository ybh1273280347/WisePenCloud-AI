# Tool 架构规范

> 一句话：业务工具只写业务逻辑，框架规则由 `tools/core/` 和 `container.py` 统一承载。

本文约束 WisePen Chat Service 当前工具体系的注册、可见性、执行和审查边界。

统一切面、后台队列、URL 缓存和工具开发流程见 [06-tool-cross-cutting-flow](06-tool-cross-cutting-flow.md)。本文只聚焦 Tool 框架主链路。

## 真实链路

当前工具链路以这些文件为准：

- `src/chat/container.py`
- `src/chat/application/tools/core/definition.py`
- `src/chat/application/tools/core/registry.py`
- `src/chat/application/tools/core/execution/dispatcher.py`
- `src/chat/application/tools/core/execution/executor.py`
- `src/chat/application/tools/tool_output_renderer.py`
- `src/chat/application/tools/tool_output_cache.py`

执行顺序：

```text
container provider
  -> ToolRegistry.register()
  -> ChatTurnCoordinator 派生 ToolScope
  -> ToolScope.schemas()
  -> LLM tool call
  -> ToolDispatcher
  -> ToolExecutor preflight
  -> tool.execute()
  -> ToolOutputRenderer
  -> ToolOutputCache
  -> RenderToolResult
```

## Tool 基本契约

业务工具实现下面这个协议即可，不需要继承框架基类：

```python
@property
def definition(self) -> ToolDefinition:
    ...

async def execute(self, context: dict[str, Any], **kwargs: Any) -> Any:
    ...
```

- `definition` 描述工具如何暴露、校验和执行。
- `execute` 只写业务逻辑。

## 统一递归渲染

普通工具直接返回普通 Python 值，例如 `dict`、`list`、dataclass、Pydantic model、scalar 或 `None`。统一工具渲染器 `ToolOutputRenderer` 会递归标准化并渲染结果。

**注意**：工具不要为了“结构化”手动序列化 JSON，也不要为普通返回值增加私有 result_builder。统一渲染就是返回边界。

## 工具族复用原则

默认原则可以记成三条：

1. 工具族之间默认解耦。
2. 工具族内部允许强复用。
3. 跨工具族复用只在核心体系边界上作为例外成立。

这里的“工具族”指围绕同一类外界交互或运行时协议形成稳定边界的一组工具，例如 web 工具族、document 工具族、session 工具族、math 工具族。

### 1. 工具族之间默认解耦

如果一段实现只服务某个工具族内部语义，就不要因为“别的工具也许也能用”而直接拿出去复用。

**例子**：不允许把 `web_fetch` 的 HTML 清洗器直接当成通用 HTML to Markdown 组件，供任意非 web 工具调用。

原因是这类实现通常隐含了该工具族自己的输入假设、缓存语义、来源约束和输出格式约束。强行跨族复用，容易把局部最优实现误包装成错误的公共抽象。

### 2. 工具族内部允许强复用

同一工具族内部，只要协议和边界一致，就可以明确复用，不需要为了“看起来更解耦”强行拆散。

**例子**：

- `platform_search`、`exa_search`、`tavily_search` 等是搜索工具族内的并列 provider 工具。
- `web_crawl` 是 `web_fetch` 的递归增强。

这类关系下，允许共享 runtime context、缓存协议、候选构建、排序实现、fetch / clean / mapping 等内部能力。这里的强耦合是有意设计，不应默认视为技术债。

### 3. 跨工具族复用是例外，不是常态

部分核心体系如果本身就是跨工具族的统一边界，可以允许例外复用。

**例子**：`document_parse` 对文档直链解析复用了 web URL 缓存。

这件事合理的原因有两个：

1. `document_parse` 和 web 工具体系同属于模型的核心 IO 工具，客观上提供了可以稳定复用的统一边界。
2. 这是架构与现实之间的必要妥协。如果不复用这条边界，文档直链几乎都要额外经过一层 `web_fetch` 转发，运行链会明显变重，而且效率很差。

所以这里复用的是已经明确承担统一协议职责的核心体系边界，而不是某个工具族内部的具体实现。

**Review 提示**：不要把个别成功的跨族复用案例，反推成“以后工具族之间都应该尽量共享实现”。

## 注册规则

新增工具必须满足：

- 放在 `src/chat/application/tools/<domain>_tools/` 或已有业务域目录下。
- 单个工具的编排入口必须挂在该业务域的顶层。
  - 顶层入口可以是 `xxx_tool.py`，也可以是与该工具同名的顶层目录配合 `xxx_tool.py`。
  - 工具内部可以有 `service.py`、`result_builder.py`、`hydrators/`、`providers/` 等实现细节目录。
  - 但不允许把一个工具再嵌进另一个工具目录里，形成“tool inside tool”的编排结构。
  - 即使两个工具是拓展关系，也仍然应该在同一业务域顶层并列存在。
- 通过 `container.py` 创建 provider。
- 加入 `tool_providers` 后由 `_build_registry()` 注册。
- 使用全局唯一的 `definition.llm_spec.name`。

不允许：

- 把业务工具放进 `tools/core/`。
- 把一个工具的编排入口挂到另一个工具的实现目录下面。
- 在工具内部创建第二套 registry、dispatcher 或 executor。
- 绕过 `ToolRegistry.derive()` 直接把全量工具 schema 交给 LLM。

**特别提醒**：搜索工具族的编排入口在 `search_tools/` 顶层并列存在；共享实现放在 `search_tools/web_search/`，不要把 provider 工具塞进另一个 provider 工具目录里。

## 可见性规则

- `ToolPolicy.expose_by_default=True`：普通请求默认可见。适用于低风险、通用、经常需要的工具。
- `ToolPolicy.expose_by_default=False`：默认隐藏。适用于 skill 工具、场景工具、成本高或能力边界窄的工具。隐藏工具只有进入 `expose_tool_name_set` 后才会出现在本轮 `ToolScope`。

当前 `ToolRegistry.derive()` 的行为要点：

- 默认隐藏工具只检查 `expose_tool_name_set`。
- 默认暴露工具受 `allow_tool_name_set` 和 `deny_tool_name_set` 过滤。
- `ToolScope.schemas()` 是本轮稳定快照，运行期 LLM 调用必须使用它。

搜索工具属于默认隐藏工具：`ChatTurnCoordinator` 只按当前用户 active 搜索凭证动态解禁一个搜索工具。平台 active 凭证解禁 `platform_search`；custom active 凭证只解禁对应 provider 工具；没有 active 搜索凭证时不暴露搜索工具。

如果将来要让 deny 也能压制隐藏工具，需要先修改 `derive()`，不能只改业务调用方。

## Preflight 规则

`ToolExecutor` 固定执行：

1. `JsonSchemaCheck`
2. `RequiredContextCheck`
3. 工具自定义 `preflight_hooks`

OpenAI function-calling JSON Schema 不支持的 one-of 参数组约束不再做成框架协议；需要这类条件参数的工具在 `execute()` 入口用工具自己的错误原因校验。

安全上下文必须来自 `context`，不能让模型通过参数传入。例如 `session_id`、`user_id`、权限范围、业务租户信息都应进入 `required_context_keys` 或可信上下文。

## 并发与副作用

当前 `ToolDispatcher` 使用 `asyncio.gather()` 并发执行同轮所有 tool call。`ToolPolicy.allow_parallel` 已存在，但当前 dispatcher 尚未按该字段调度。

因此新增有副作用工具时必须特别审查：

- 是否写外部系统。
- 是否依赖同一资源顺序。
- 是否可能并发创建重复数据。
- 是否需要在 dispatcher 层补串行策略后才能上线。

## 新增工具 Review 清单

| 检查项 | 说明 |
| --- | --- |
| `name` | 是否全局唯一且语义清楚。 |
| `description` | 是否说明何时使用，而不是堆实现细节。 |
| JSON Schema | 是否是 object，`required` 是否只引用已定义字段。 |
| `timeout_seconds` | 是否声明。 |
| 安全上下文 | 是否走 `required_context_keys`。 |
| 普通结构化结果 | 是否交给统一递归渲染，而不是工具内手动转 result。 |
| 大文本 | 是否按 `ToolReturn.cacheable_texts` 交给统一切面。 |
| provider 注册 | 是否误把工具内部 helper 注册成 container provider。 |
| 默认暴露 | 是否需要默认暴露；如果不是，谁负责加入 `expose_tool_name_set`。 |

## 当前稳定工具约定

### `tool_content_rerank_read` / `tool_content_regex_read`

- 默认暴露。
- 只通过 `content_ids` 批量读取 `cnt_*`。
- 一次调用内所有 `content_ids` 共用同一组读取参数。
- `tool_content_rerank_read` 只做自然语言重排检索，必填 `query`。
- `tool_content_regex_read` 只做正则精确匹配，必填 `pattern`。
- 两个工具都不再暴露 `mode` 路由字段。
- 单项读取失败返回 failed item，不拖垮整次工具调用。

### `document_parse`

- 默认暴露。
- 只接受 `file_refs: tfile_*[]` 或 `direct_urls: http(s)[]`，二者互斥。
- `file_refs` 通过 `ToolRunFileStore.resolve_ref(...)` 解析真实文件路径。
- `direct_urls` 只接受明显非 HTML 文档文件直链 URL，下载后复用同一文件解析链。
- `file_refs` 与 `direct_urls` 互斥；普通 HTML 页面仍使用 `web_fetch` / `web_crawl`。
- web 来源的解析结果必须回写统一 URL 缓存路径。
- 内部并发解析，单项失败返回 failed item。
- 成功文件的 Markdown 进入 `ToolReturn.cacheable_texts`，由输出缓存切面分批生成多个 `cnt_*`。
- 实现结构保持轻量：顶层 `document_parse_tool.py` 是工具门面；`document_parse/service.py` 负责解析路由；`document_parse/models.py`、`errors.py`、`cache.py` 放在该能力包顶层；`document_parse/parsers/` 下再区分 `common_document/` 和 `specialized/`。

### `image_ocr`

- 默认暴露。
- 只在模型看图后仍需要精确抽取图片文字时使用。
- 只接受 `file_ref: tfile_*` 或 `file_path`，二者互斥。
- `file_ref` 走 `ToolRunFileStore.resolve_ref(...)`；`file_path` 只接受用户直接给出的 URL/路径或可信上游路径。
- OCR Markdown 进入 `ToolReturn.cacheable_texts`，不直接塞进 `visible_result`。
- OCR provider 保持在 `document_tools/ocr/`，与 `document_parse/` 平行；它服务 PDF 扫描页 OCR 和独立 `image_ocr`，不放进 parser 树。

### `math_tools`

- 默认暴露。
- 拆成 `calculus_solver`、`linear_algebra_solver`、`equation_solver`、`stats_solver`、`expression_solver` 5 个窄工具。
- 工具门面只负责 schema、description、policy 和 service 调度。
- 无状态 service 负责 SymPy / NumPy / SciPy 调用。
- 固定 task 集合使用 `StrEnum`，schema 和 service 从同一枚举来源读取。
- `core/` 放工具外壳、错误和 task 枚举；`_utils/` 放表达式解析和 payload 读取；`solvers/` 放具体 solver。
- 同类 helper 聚合为清晰命名模块，例如 `expression_parser.py` 和 `payload_readers.py`。
- 普通结果返回 dataclass，由统一递归渲染处理。

## 引用协议

工具之间的文件传递必须使用 `tfile_*`；工具之间的大文本传递必须使用 `cnt_*`。不得把本地路径、base64、OSS key 或工具私有缓存 ID 混入这两个协议。
