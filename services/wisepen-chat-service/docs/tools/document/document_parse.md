# document_parse

> 一句话：`document_parse` 把 `tfile_*` 或明显文件直链批量解析为 Markdown，不读普通 HTML，也不负责上传或资产持久化。

实现入口：`src/chat/application/tools/document_tools/document_parse_tool.py`

`document_parse` 将上游工具产出的 `tfile_*` 临时文件引用，或明显的文件直链 URL，批量解析为 Markdown。文件直链只支持完整 `http(s)` 非 HTML 文件 URL；普通网页仍交给 `web_fetch` / `web_crawl`。

## 何时使用

- 已经有一个或多个 `tfile_*`，需要把文件内容转为可检索 Markdown。
- 用户直接给出明显文档文件直链（PDF、Office、表格等）并要求读取文件内容时，直接传 `direct_urls`，不要先走 `web_fetch` 生成中转 `tfile_*`。
- 同一任务有多个文件时，应一次性把同一来源字段下的所有文件传入同一调用。
- 解析结果较长时，后续优先通过 `tool_content_read` 检索相关窗口，或通过 `tool_content_sequential_read` 顺序继续阅读单个 `cnt_*`。

## 参数

| 参数 | 类型 | 规则 |
| --- | --- | --- |
| `file_refs` | `string[]` | 支持批量 `tfile_*`；超单批时工具内部自动分批。 |
| `direct_urls` | `string[]` | 支持批量完整 `http(s)` 文档文件直链；超单批时工具内部自动分批。 |

`file_refs` 和 `direct_urls` 必须二选一。执行上下文必须包含 `user_id` 和 `session_id`。工具会用这两个值解析并校验 `tfile_*` 的作用域；直链会先下载到短期工具文件，再复用同一解析链路。

## 与 web_fetch 的关系

`web_fetch` 和 `document_parse` 共同构成核心外界信息获取工具体系：`web_fetch` 负责网页正文和不确定 URL 的抓取，`document_parse` 负责文件内容解析。两者共享 URL 内容缓存、HTTP fetcher 能力和 `source_*` metadata 是有意设计的正确行为，不视为需要拆除的错误耦合。

直链解析会先按 URL 读取 parse markdown 缓存；未命中时使用工具层共享 URL fetcher 下载文件，预创建同一 URL 缓存文档，再把解析出的 Markdown 回填到该 URL 缓存路径。

URL 缓存公共组件位于：

```text
src/chat/application/tools/common/web_content_cache/
```

`document_parse` 通过 `DocumentParseCache` 使用同一套 Redis entry + Mongo value 缓存：

- `file_refs`：按 `tfile_*` metadata 中的 `source_kind/source_scope/source_url/source_cache_doc_id` 精确读取和回写 parsed Markdown。
- `direct_urls`：先读 URL parsed cache；未命中时下载文件、写非 HTML 占位，再解析并回填。
- stale parsed cache 命中时先返回旧 Markdown，再通过 Arq 队列触发 `refresh_document_parse_cache` 后台刷新。

document parse 读取缓存时不能在 public/private 域之间回退，避免自定义搜索源或用户私有 URL 结果串域。

## 输出

返回 `ToolReturn(tag="document_parse_result")`：

| 字段 | 说明 |
| --- | --- |
| `visible_result.items` | 按输入顺序返回每个文件的 `source`、`status`、`file_name`、`source_scope` 和失败细节。 |
| `visible_result.suggested_action` | 建议后续用 `tool_content_read` 的 `ranked_expand` 模式读取解析结果。 |
| `cacheable_texts` | 每个成功文件一段 Markdown；当总长度超过内联阈值时会被缓存为独立的 `cnt_*` receipt。 |

## 边界

- `file_refs` 只解析 `tfile_*` 指向的短生命周期文件。
- `direct_urls` 只用于明显文档文件直链，不用于普通 HTML 页面。
- 不负责文件上传、资产持久化、知识库入库或文件展示。
- 单个文件解析失败会记录为 failed item，不阻断其它文件。
- 内部最多并发解析 8 个文件；大量输入会按内部批次切分后顺序聚合。

## 解析策略

解析路由由 `DocumentParseService` 直接决定：

| 文件类型 | 策略 |
| --- | --- |
| PDF | 专职 PDF 策略，内部自行维护 PyMuPDF4LLM/OCR 兜底 |
| XLSX | Pandas |
| 图片 | 不作为通用文档解析入口；模型看图后需要精确抽字时使用 `image_ocr` |
| 其它普通文档 | Docling -> MarkItDown |

`parsers/common/` 放通用解析器：Docling 和 MarkItDown；`parsers/specialized/` 放格式或策略专用解析器：PDF、XLSX。通用 Docling 不维护额外 `allowed_formats` 白名单。PDF、XLSX 等专用路径不追加通用 MarkItDown 兜底；专用解析器如果需要特殊兜底，应在自己的策略内部维护，避免专用行为反向污染通用解析链路。

OCR provider 不属于 parser 树，统一放在 `document_tools/ocr/`。PDF 扫描页和 `image_ocr` 工具都复用这个辅助能力。

### PDF 主链路

- 使用 Docling，开启表格结构和图片抽取，关闭 Docling OCR。
- PDF 内部只按页判断是否存在可抽取文本；空文本页视为扫描页，不再用图片覆盖度阈值推断。
- 文本页优先保留 Docling 结构化结果和已抽取图片，不因为页面存在大图而强行 OCR。
- 扫描页在原页位用 OCR 替换或补全。
- Docling 单页空结果再用 PyMuPDF4LLM 逐页补页。
- 可分页文档尽量按页插入 `<!-- page N -->` 标记；Docling 解析结果存在 `pages` 时按 `page_no` 分页导出后再注入页码，无可靠页信息的格式保持原始 Markdown 输出。
- PyMuPDF4LLM 兜底链路按页单独解析，避免单页异常拖垮整份 PDF。
- Docling Markdown 导出固定保留已抽取图片，尽量把图片写成 data URI；如果上游格式或 Docling pipeline 无法生成图片对象，才会退化为普通 Markdown 占位。
- 如果后续需要专门识别表格截图、图表或图片内复杂结构，应新增平行工具承载该能力，不反向扩大 PDF 文本解析策略。

### OCR 边界

- OCR 不作为 document_parse 的全局兜底 parser。
- 独立图片文字提取走平行工具 `image_ocr`，不作为 document_parse 的普通兜底。
- PDF 扫描页 OCR 保留在 `PdfParseStrategy` 内部，以便和 Docling/PyMuPDF4LLM 文本页结果按原页序合并。

### 开发环境提示

本地开发机上 Docling native 层偶发 `std::bad_alloc` 通常表示本机内存紧张，不代表 PDF 主链路设计不可用；容器环境资源更稳定，实测该链路可稳定运行。

## 统一切面

- 工具门面不手写 `cnt_*` receipt；大文本缓存由 `ToolOutputCache` 和 `ToolContentStore` 统一处理。
- URL cache 的 Mongo `doc_id`、Redis key 和 `source_cache_doc_id` 不暴露给模型；它们只在工具内部 metadata 中流转。
