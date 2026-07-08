# image_ocr

> 一句话：`image_ocr` 只在模型看图后仍需要精确抽取图片文字时使用，不替代主模型多模态理解，也不解析文档。

实现入口：`src/chat/application/tools/document_tools/image_ocr_tool.py`
OCR provider：`src/chat/application/tools/document_tools/ocr/`

`image_ocr` 是 document 工具域里的按需辅助工具。它接收内部 `tfile_*` 图片引用，或用户直接给出的图片 URL/路径，调用 OCR provider 产出 Markdown 文本。

## 何时使用

- 模型已经拿到图片，但需要更精确的图片内文字。
- 上游工具返回了图片 `tfile_*`，后续任务依赖图片里的文字。
- 用户直接给出图片 URL，并明确要求识别其中的文字。

## 不要在这些场景使用

- 普通图片理解、多模态问答可以直接由主模型完成。
- PDF、Office、XLSX 等文档解析使用 `document_parse`。
- 表格截图、图表结构识别等复杂视觉解析应新增平行专用工具，不塞进 OCR 文本抽取工具。

## 参数

| 参数 | 类型 | 规则 |
| --- | --- | --- |
| `file_ref` | `string` | 内部 `tfile_*` 图片引用。 |
| `file_path` | `string` | 用户直接给出的图片 URL/路径，或可信上游工具路径。 |

`file_ref` 和 `file_path` 在工具 `execute()` 入口校验：二者必须且只能提供一组。`file_ref` 通过 `ToolRunFileStore.resolve_ref(...)` 校验 `user_id/session_id` 作用域；URL 形式的 `file_path` 使用工具层共享 URL fetcher 下载。

## 输出

返回 `ToolReturn(tag="image_ocr_result")`：

| 字段 | 说明 |
| --- | --- |
| `visible_result.status` | `success` 或 `failed`。 |
| `visible_result.file_name` | 识别文件名。 |
| `visible_result.reason` | 失败原因，例如 `invalid_file_ref`、`not_image`、`ocr_failed`。 |
| `cacheable_texts` | 成功 OCR 后的 Markdown；大文本由统一输出缓存生成 `cnt_*`。 |

OCR Markdown 不直接放进 `visible_result`，避免大文本污染模型上下文。

## 内部机制

```text
file_ref
  -> ToolRunFileStore.resolve_ref
  -> MIME check
  -> OCR client
  -> cacheable_texts

file_path URL
  -> tools/utils/url/security.validate_public_http_url
  -> tools/utils/url/fetcher.fetch_url
  -> temp file
  -> MIME check
  -> OCR client
  -> cacheable_texts
```

`ImageOcrToolResult` 自身携带 `markdown`，工具门面只在最终返回时把 Markdown 转入 `ToolReturn.cacheable_texts`，不再用额外 tuple 表达隐式关系。

## 边界

- OCR provider 是 `document_tools/ocr/` 下的辅助能力，不属于 `document_parse/parsers/`。
- `ToolRunFileStore` 相关错误统一通过 `tool_file_error_reason(...)` 映射为模型可见 reason。
- URL 下载能力复用 `tools/utils/url/fetcher.py`，不依赖 `web_fetch` 私有 fetcher；URL 安全性校验复用 `tools/utils/url/security.py`，不做页面内容阻断。
