# Code Review 地图：application 工具与团队规范

> 这份地图不是规范本身，而是帮你快速找到「这次 review 该看哪份文档」的导航。如果你是第一次 review 这个模块，建议从这里开始。

## 一、按角色选阅读路径

### 路径 A：我刚拿到一个 PR，想快速判断有没有踩红线

1. 先扫本目录下的 **快速检查卡**（每个规范开头都有）
2. 再看 [01-tool-architecture](01-tool-architecture.md) 的「新增工具 Review 清单」
3. 如果改动了返回值、缓存或 `cnt_*`/`tfile_*`，转到 [02-tool-return-and-content](02-tool-return-and-content.md)
4. 如果新增 provider 或 settings，转到 [04-container-and-settings](04-container-and-settings.md)

预计耗时：5–10 分钟可完成初筛。

### 路径 B：我要新增/扩展一个工具

1. 先读 [06-tool-cross-cutting-flow](06-tool-cross-cutting-flow.md) 的「标准开发流程」
2. 确定工具所属业务域后读 [01-tool-architecture](01-tool-architecture.md) 的「注册规则」
3. 需要排序/分块/轻量 LLM 时查 [05-utils-inventory](05-utils-inventory.md)
4. 搜索类工具额外读 [07-web-search-extension](07-web-search-extension.md)
5. 写文档时对照 [tools/toolchain_architecture](../tools/toolchain_architecture.md) 的「Tool 文档模板」

### 路径 C：我想理解整条工具链路是怎么跑起来的

1. [06-tool-cross-cutting-flow](06-tool-cross-cutting-flow.md) 的「总原则」和「统一切面清单」
2. [toolchain_architecture](../tools/toolchain_architecture.md) 的「Runtime 信封」和「工具族流程」
3. [01-tool-architecture](01-tool-architecture.md) 的「真实链路」
4. [02-tool-return-and-content](02-tool-return-and-content.md) 的「返回值原则」和「分批缓存规则」

## 二、规范文档速览

| 文档 | 解决什么问题 | 最常查阅的章节 |
| --- | --- | --- |
| [01-tool-architecture](01-tool-architecture.md) | Tool 怎么注册、怎么暴露、怎么执行 | 注册规则、可见性规则、新增工具 Review 清单 |
| [02-tool-return-and-content](02-tool-return-and-content.md) | 返回值怎么交给模型、大文本怎么缓存 | ToolReturn 使用边界、分批缓存规则、tool_content_read 规则 |
| [03-shared-engines-and-dev-flow](03-shared-engines-and-dev-flow.md) | 共享引擎该做什么、新增能力放哪 | 共享引擎边界、开发流程判断顺序、review 清单 |
| [04-container-and-settings](04-container-and-settings.md) | 什么该进 container、settings 怎么分 | Container 注册原则、Settings 边界、Review 清单 |
| [05-utils-inventory](05-utils-inventory.md) | 现成能力在哪、能不能直接用 | 快速定位、Chunking/Ranking/LLM Clients 入口 |
| [06-tool-cross-cutting-flow](06-tool-cross-cutting-flow.md) | 工具调用穿过了哪些统一切面 | 统一切面清单、标准开发流程、外界信息工具流程 |
| [07-web-search-extension](07-web-search-extension.md) | 搜索体系怎么扩展 | 新增普通搜索源、新增专用搜索工具、禁止事项 |

## 三、关键概念对照表

| 概念 | 一句话解释 | 相关文档 |
| --- | --- | --- |
| `ToolReturn` | 需要托管大文本时用的返回值包装 | [02](02-tool-return-and-content.md)、[06](06-tool-cross-cutting-flow.md) |
| `cnt_*` | 会话内短期大文本读取凭证 | [02](02-tool-return-and-content.md)、[toolchain](../tools/toolchain_architecture.md) |
| `tfile_*` | 工具间临时文件引用 | [02](02-tool-return-and-content.md)、[06](06-tool-cross-cutting-flow.md) |
| `search_ref` | 搜索候选到真实 URL 的短期映射 | [07](07-web-search-extension.md)、[toolchain](../tools/toolchain_architecture.md) |
| `web_content_cache` | URL 内容的跨工具复用缓存 | [06](06-tool-cross-cutting-flow.md)、[toolchain](../tools/toolchain_architecture.md) |
| 工具族 | 围绕同一类外界交互形成稳定边界的一组工具 | [01](01-tool-architecture.md)、[toolchain](../tools/toolchain_architecture.md) |
| 统一切面 | 所有工具共享的渲染、缓存、校验、存储等横切逻辑 | [06](06-tool-cross-cutting-flow.md) |

## 四、常见 Review 场景索引

### 「这个改动要不要进 container？」

→ [04-container-and-settings](04-container-and-settings.md) 的「Container 注册原则」和「Review 清单」。

### 「这个返回值该不该用 ToolReturn？」

→ [02-tool-return-and-content](02-tool-return-and-content.md) 的「ToolReturn 使用边界」。

### 「这段排序/分块逻辑能不能自己写？」

→ [05-utils-inventory](05-utils-inventory.md) 的「快速定位」，然后读 [03-shared-engines-and-dev-flow](03-shared-engines-and-dev-flow.md) 的「review 时怎么判断是否重复造轮子」。

### 「新增了一个搜索 provider，流程对吗？」

→ [07-web-search-extension](07-web-search-extension.md) 的「如何新增一个普通搜索源」。

### 「这个工具能不能直接读另一个工具的缓存？」

→ [06-tool-cross-cutting-flow](06-tool-cross-cutting-flow.md) 的「外界信息工具流程」和 [toolchain](../tools/toolchain_architecture.md) 的「三类引用」。

### 「文档该放 docs 的哪个目录？」

→ [03-shared-engines-and-dev-flow](03-shared-engines-and-dev-flow.md) 的「开发流程判断顺序」。

## 五、与 tools/ 文档的关系

- `docs/team/`：团队必须共同遵守的工程规范（约束当前仓库如何演进）。
- `docs/tools/`：单个工具的使用边界、内部机制和协作链（面向具体实现和模型提示词）。
- `docs/tools/toolchain_architecture.md`：跨工具公共机制和总体架构图。

Review 时，先看 team 规范判断是否踩红线；再看 tools 具体文档判断实现是否符合工具级契约。
