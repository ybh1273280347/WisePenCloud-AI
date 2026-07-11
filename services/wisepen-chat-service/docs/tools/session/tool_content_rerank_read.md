# tool_content_rerank_read

> 一句话：按自然语言 query 在一个或多个 `cnt_*` 中做跨文档重排检索，不创建新 receipt。

实现入口：`src/chat/application/tools/session_tools/tool_content_rerank_read_tool.py`

`tool_content_rerank_read` 从 `ToolContentStore` 中读取已有 `cnt_*` 内容。它用于上一轮工具返回 `content_receipts` 后，对一个或多个内容做跨文档语义检索。

## 何时使用

- 工具输出太长，模型只拿到了 `cnt_*` receipt。
- 需要在一个或多个缓存内容中按自然语言问题找相关窗口。
- 需要跨多个内容做全局相关性排序。

## 参数

| 参数 | 类型 | 规则 |
| --- | --- | --- |
| `content_ids` | `string[]` | 必填，1 到 64 个 `cnt_*`。超单批时工具内部自动分批。 |
| `selector` | `object` | 可选，按结构元数据预筛选 chunk。 |
| `query` | `string` | 必填，自然语言检索问题。 |
| `top_k` | `integer` | 返回全局排序后的 match 数，默认 5。 |
| `merge_before` / `merge_after` | `integer` | 对中心 chunk 前后扩展的 chunk 数。 |

`selector` 支持 `block_kinds`、`sections`、`page_labels`、`anchor_labels` 和 `chunk_indices`。多个 selector 组之间取交集。

执行上下文必须包含 `session_id`。

## 输出

返回 `ToolContentReadResult`：

| 字段 | 说明 |
| --- | --- |
| `matches` | 跨全部 `content_ids` 的全局有序命中列表。 |
| `matches[*].content_id` | 该命中来自哪个 `cnt_*`。 |
| `matches[*].window` | 命中的窗口文本与定位信息。 |
| `failed` | 单项不可读、过期或不存在的 `content_id` 列表。 |

## 边界

- 只读取已有 `cnt_*`，不会创建新的 content receipt。
- 只能读取同一 `session_id` 下的内容；不存在、过期或跨会话内容会按单项失败返回。
- 使用 ranking engine 对全部候选 chunk 做跨文档全局排序，不访问外部搜索源。
- 需要正则精确匹配时，使用 `tool_content_regex_read`。
- 需要按 offset 顺序继续读单个内容时，使用 `tool_content_sequential_read`。
