# 团队规范索引

本目录记录 WisePen Chat Service 当前需要团队共同遵守的工程规范。它不关心历史背景，只回答一个问题：**这个仓库现在应该怎么写代码**。

> 第一次 review？先看 [REVIEW_MAP](REVIEW_MAP.md)，它会告诉你该读哪一篇。

## 规范文档一览

| 文档 | 适合回答的问题 |
| --- | --- |
| [01-tool-architecture](01-tool-architecture.md) | Tool 怎么注册、怎么暴露、怎么执行、工具族之间怎么复用 |
| [02-tool-return-and-content](02-tool-return-and-content.md) | 工具返回什么、什么时候用 `ToolReturn`、大文本怎么缓存和读取 |
| [03-shared-engines-and-dev-flow](03-shared-engines-and-dev-flow.md) | 共享引擎该做什么、新增能力该放哪、怎么判断重复造轮子 |
| [04-container-and-settings](04-container-and-settings.md) | 什么对象该进 `container.py`、settings 怎么分层 |
| [05-utils-inventory](05-utils-inventory.md) | 当前已经沉淀的共享能力入口在哪里 |
| [06-tool-cross-cutting-flow](06-tool-cross-cutting-flow.md) | 一个 tool call 穿过哪些统一切面、标准开发流程是什么 |
| [07-web-search-extension](07-web-search-extension.md) | 搜索体系怎么新增 provider、怎么新增专用搜索工具 |

## 快速检查卡

下面这几条是最常 review 时踩线的约束。如果不确定，就回头查对应文档。

### 运行入口

- 应用级依赖图入口只有一个：`src/chat/container.py`。
- Tool 框架能力集中在 `src/chat/application/tools/core/`，业务工具不要回写框架规则。

### 工具返回值

- 普通结构化结果直接返回 Python 值（`dict`、dataclass、Pydantic model、list、scalar、`None`）。
- 只有需要托管大文本时才返回 `ToolReturn`。
- 不要为普通返回值手动转 result payload，也不要手写 XML。

### 大文本与文件

- 大文本读取统一走 `ToolContentStore` 和 session 内容读取工具。
- 工具间文件传递统一用 `tfile_*`。
- 不要把本地路径、base64、OSS key 或工具私有缓存 ID 混进这两个协议。

### 共享引擎

- 共享引擎只承担共享基础能力。
- 新增工具前先查 `05-utils-inventory`，不要重复实现已有能力。

### 统一切面

- preflight、渲染、输出缓存、`ToolContentStore`、`ToolRunFileStore`、`web_content_cache` 和 GC 都不是单个工具的私有逻辑。
- 工具实现前先确认这些切面能不能表达需求，再决定要不要写新业务代码。

### 文档迁移方案

- 文档、网页、搜索、文件解析等迁移方案只能作为设计参考，不能覆盖本目录规范。
