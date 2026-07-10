# document_parse

> 一句话：`document_parse` 将统一 `file_*` 引用或明显文档直链转换为 Markdown，不接收模型透传的本地路径。

实现入口：`src/chat/application/tools/document_tools/document_parse_tool.py`

## 输入边界

`document_parse` 保持两个互斥入口：

```json
{"file_refs": ["file_xxx"]}
```

```json
{"direct_urls": ["https://example.com/report.pdf"]}
```

- `file_refs` 只接受受信工具产生的 `file_*` 引用，通过 `FileReferenceStore.resolve_ref(...)` 校验用户、会话和文件完整性。
- `direct_urls` 只接受公开 `http(s)` 文档文件 URL；普通网页仍使用 `web_fetch` / `web_crawl`。
- 模型不得传入或伪造本地路径、OSS key、上传对象 ID 或缓存内部 ID。
- 单次调用只能提供 `file_refs` 或 `direct_urls` 中的一组。

`file_*` 是统一文件引用协议，不绑定某一种持久化实现。当前后端将引用解析为本机可读路径；后续可接入沙箱文件等来源而不改变模型参数。

## 内部流程

```text
file_*
  -> FileReferenceStore.resolve_ref
  -> local Path + metadata
  -> DocumentConverterRouter
  -> Markdown

direct URL
  -> URL 安全校验和 parsed cache
  -> 限流下载到本次调用临时文件
  -> DocumentConverterRouter
  -> URL parsed cache
  -> 删除下载临时文件
```

直链下载后直接进入 converter，不创建仅供本次调用使用的中间 `file_*`。

## Converter 路由

转换器位于：

```text
document_parse/converters/
  base.py
  router.py
  pdf/mineru_converter.py
  spreadsheet/spreadsheet_converter.py
  office/docx_converter.py
  office/pptx_converter.py
  html/html_converter.py
  json/json_converter.py
  plaintext/plaintext_converter.py
  fallback/fallback_converter.py
```

精确路由：

| 格式 | Converter | 实现 |
| --- | --- | --- |
| PDF | `MinerUConverter` | MinerU 云端上传、轮询、ZIP Markdown 提取 |
| DOCX | `DocxConverter` | Docling，图片 Base64 内嵌 |
| PPTX | `PptxConverter` | Docling，图片 Base64 内嵌 |
| CSV / TSV / XLS / XLSX | `SpreadsheetConverter` | pandas；文本表格严格解码并保留字符串值 |
| HTML / HTM | `HtmlConverter` | MarkItDown 完整文档转换，不使用网页正文清洗器 |
| JSON / JSONL / NDJSON | `JsonConverter` | 标准库验证和规范化 |
| TXT / Markdown / 常见代码和配置 | `PlaintextConverter` | `read_bytes + decode_text`，保持原文 |

未命中精确格式时按以下顺序兜底：

```text
Docling -> MarkItDown -> 严格文本解码 -> UnsupportedDocumentFormatError
```

图片、压缩包、音视频、可执行文件、共享库、字体和数据库等在进入通用 fallback 前明确拒绝。图片文字提取使用独立 `image_ocr`。

## MinerU PDF

PDF 不再执行本地 Docling、PyMuPDF4LLM 或 PaddleOCR fallback。流程为：

```text
POST /api/v4/file-urls/batch
  -> PUT 签名上传 URL
  -> GET /api/v4/extract-results/batch/{batch_id}
  -> 下载受大小限制的 ZIP
  -> 优先读取 full.md，或唯一 Markdown 文件
  -> 使用 content_list.json 的 page_idx 注入 <!-- page N -->
```

MinerU 使用独立 `httpx.AsyncClient` 资源。API token、base URL、轮询间隔、任务/上传/下载超时和最大下载字节数来自 settings。日志和模型输出不包含 token 或签名 URL。

页码从 1 开始，并插在每页第一个非空正文 Markdown 块之前。只有所有页面都能在最终 Markdown 中唯一且顺序定位时才注入；content list 缺失、结果文件错配或任一页定位不可靠时，完整返回 MinerU 原始 Markdown，不输出部分或推测页码。图片、表格、代码等块仅用于定位，内容仍交给后续 chunking engine 处理。

## 输出与缓存

工具返回 `ToolReturn(tag="document_parse_result")`：

- `visible_result.items`：按输入顺序返回 `source`、`status`、`file_name` 和失败 `reason`。
- 每个成功文件对应一段 `cacheable_texts`，由 `ToolOutputCache` 内联或生成独立 `cnt_*`。
- web 来源继续复用统一 URL parsed cache；缓存 key 不暴露给模型。
- 单项失败不阻断同批其它文件。

## 非职责

- 不负责用户附件、资产持久化、OSS 上传或知识库入库。
- 不自动解压归档。
- 不执行 HTML JavaScript，不启动浏览器，不主动抓取 HTML 外部资源。
- 不允许模型通过工具参数传递本地文件路径。
