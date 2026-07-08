# tool_content_regex_read

> 一句话：按 Python 正则在一个或多个 `cnt_*` 中做跨文档精确匹配，不创建新 receipt。

实现入口：`src/chat/application/tools/session_tools/tool_content_regex_read_tool.py`

`tool_content_regex_read` 从 `ToolContentStore` 中读取已有 `cnt_*` 内容。它用于上一轮工具返回 `<content_receipt>` 后，对一个或多个内容做正则匹配并展开命中窗口。

## 何时使用

- 工具输出太长，模型只拿到了 `cnt_*` receipt。
- 需要在一个或多个缓存内容中精确查找 ID、URL、标题、姓名、引用片段或固定格式文本。
- 用户明确给出可用正则或需要精确模式匹配。

## 参数

| 参数 | 类型 | 规则 |
| --- | --- | --- |
| `content_ids` | `string[]` | 必填，1 到 64 个 `cnt_*`。超单批时工具内部自动分批。 |
| `selector` | `object` | 可选，按结构元数据预筛选 chunk。 |
| `pattern` | `string` | 必填，Python 正则，最长 500 字符。 |
| `max_matches` | `integer` | 跨全部 `content_ids` 的最大匹配窗口数，默认 10。 |
| `merge_before` / `merge_after` | `integer` | 对中心 chunk 前后扩展的 chunk 数。 |

`selector` 支持 `block_kinds`、`sections`、`page_labels`、`anchor_labels`、`chunk_indices` 和 `include_unknown`。多个 selector 组之间取交集。

执行上下文必须包含 `session_id`。

## 输出

返回 `ToolContentReadResult`：

| 字段 | 说明 |
| --- | --- |
| `matches` | 跨全部 `content_ids` 的命中列表。 |
| `matches[*].content_id` | 该命中来自哪个 `cnt_*`。 |
| `matches[*].window` | 命中的窗口文本与定位信息。 |
| `failed` | 单项不可读、过期或不存在的 `content_id` 列表。 |

## 边界

- 只读取已有 `cnt_*`，不会创建新的 content receipt。
- 只能读取同一 `session_id` 下的内容；不存在、过期或跨会话内容会按单项失败返回。
- 这是跨文档精确模式匹配，不适合模糊语义搜索。
- 需要自然语言相关性检索时，使用 `tool_content_rerank_read`。
- 需要按 offset 顺序继续读单个内容时，使用 `tool_content_sequential_read`。
