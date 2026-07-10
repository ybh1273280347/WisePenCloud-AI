# web_fetch

> 一句话：`web_fetch` 批量抓取独立 URL，HTML 返回清洗后的 Markdown，非 HTML 文件发布为 `file_*` 供 `document_parse` 解析。

实现入口：`src/chat/application/tools/web_tools/web_fetch_tool.py`
内部服务：`src/chat/application/tools/web_tools/fetch_services/web_fetch.py`

`web_fetch` 批量抓取一组独立 URL。它是外界信息获取链中的正文抓取工具，不负责搜索候选、不递归爬站、不直接解析 PDF/Office 内容。

## 何时使用

- 用户给出普通网页 URL，并要求读取页面内容。
- 搜索工具返回了候选 URL，需要把候选变成可验证正文。
- URL 类型不确定，需要先探测是 HTML 还是文件。

## 不要在这些场景使用

- 用户给出明显文档文件直链并要求读文件内容：直接用 `document_parse(direct_urls=[...])`。
- 用户给出明显图片并且需要精确抽字：用 `image_ocr(file_path=...)`。
- 用户需要多页站点采集：用 `web_crawl`。
- 用户只需要搜索候选：用 `platform_search` 或供应商搜索工具。
- 已有 `cnt_*`：用 session 读取工具。

## 参数

| 参数 | 类型 | 规则 |
| --- | --- | --- |
| `urls` | `string[]` | 直接抓取一批完整 `http(s)` URL；超单批时工具内部自动分批。 |
`urls` 必填；搜索工具输出的候选 URL 直接作为该参数传入。

## 内部运行机制

```text
input urls
  -> URL validation
  -> FetchCoordinator.fetch_many
  -> per URL: WebContentCacheService.read_markdown_page
  -> static page fetch
  -> optional browser page fetch
  -> HTML: trafilatura clean + quality check + cache write
  -> non-HTML: temporary file download
  -> non-HTML: FileReferenceStore publish + cache stub write
  -> ToolReturn(cacheable_texts=markdowns)
```

抓取链路先用静态页面 fetcher 读取 HTML，质量不足时再降级到浏览器页面 fetcher。只有静态页面 fetcher明确发现目标不是 HTML 时，才交给临时文件下载器落盘并发布 `file_*`。HTML 由 `TrafilaturaCleaner` 清洗为 Markdown，并按 HTTP cache-control 计算 URL 缓存 TTL。

内部服务结构：

| 关注点 | 入口 |
| --- | --- |
| web_fetch 服务门面 | `web_tools/fetch_services/web_fetch.py` |
| web_crawl 服务门面 | `web_tools/fetch_services/web_crawl.py` |
| 共享模型 | `web_tools/fetch_services/core/models.py` |
| 共享异常 | `web_tools/fetch_services/core/errors.py` |
| 非 HTML 临时文件下载 | `web_tools/fetch_services/downloaders/temp_file_downloader.py` |
| 静态 HTML 抓取 | `web_tools/fetch_services/fetchers/static_page_fetcher.py` |
| 浏览器 HTML 抓取 | `web_tools/fetch_services/fetchers/stealthy_page_fetcher.py` |
| HTML cleaner | `web_tools/fetch_services/cleaners/trafilatura_cleaner.py` |
| URL 缓存适配 | `web_tools/fetch_services/infra/cache.py` |
| 批量调度器 | `web_tools/fetch_services/infra/batch_scheduler/` |

URL 缓存编排已经收敛到工具公共切面：

```text
src/chat/application/tools/common/web_content_cache/
```

其中 Redis value 直接保存 raw HTML、Markdown、metadata 和统一 TTL。Redis value 未过期时命中缓存，过期后视为未命中并重新抓取。

非 HTML 文件不会被 `web_fetch` 解析。它会：

1. 下载到临时文件。
2. 为 URL 写入缓存占位文档。
3. 发布为 `file_*`，metadata 包含 `source_kind=web_fetch`、`source_scope`、`source_url`。
4. 返回 `file_ref` 和 `file_label`，建议下一步调用 `document_parse`。

## 输出

返回 `ToolReturn(tag="web_fetch_result")`：

| 字段 | 说明 |
| --- | --- |
| `visible_result.items` | 每个成功 URL 的轻量元数据，包含 `source_url`、`title`、`file_ref`、`file_label`。 |
| `visible_result.failed` | 单 URL 失败列表；批量中单项失败不阻断其它 URL。 |
| `visible_result.warnings` | 批量级 warning。 |
| `cacheable_texts` | HTML Markdown。超出内联阈值后变成 `cnt_*`。 |

visible result 不直接携带 Markdown，避免大正文污染模型上下文。

## 工具链协作

- `platform_search/exa_search/... -> web_fetch(urls=[...])`：标准搜索证据链。
- `web_fetch -> document_parse(file_refs=[...])`：不确定 URL 命中非 HTML 文件后的解析链。
- `web_fetch -> tool_content_rerank_read / tool_content_regex_read`：HTML 正文进入 `cnt_*` 后的跨文档内容检索链；命中具体内容后可继续调用 `tool_content_sequential_read`。
- 与 `document_parse(direct_urls=[...])` 共享 URL 缓存和 fetcher 能力，这是正确的强耦合。

## 可插拔组件

- `fetch_services/downloaders/temp_file_downloader.py`：非 HTML 临时下载，可实验 header、MIME 探测和最大响应字节。
- `tools/utils/url/security.validate_public_http_url`：URL 安全性校验，只校验 URL 本身，不做页面内容阻断。
- `fetch_services/fetchers/static_page_fetcher.py` / `stealthy_page_fetcher.py`：静态与浏览器 HTML 抓取，可实验 impersonate、browser 并发和反爬策略。
- `fetch_services/cleaners/trafilatura_cleaner.py`：web_fetch 内部 HTML 正文抽取，可替换 cleaner。
- `judge_quality`：降级判断阈值，可按站点类型或内容长度实验。
- `WebContentCacheService`：统一 URL 缓存门面，可扩展 ETag、Last-Modified、缓存分层。
- `web_content_cache/core/protocols.py`：定义缓存 active 索引和正文存储协议。
- `RedisWebContentCacheRepository`：协议对应的 Redis 持久化实现。

## 后续优化

- 在提示词中持续强调 obvious document file URL 直接走 `document_parse(direct_urls=[...])`。
- 给非 HTML handoff 增加更明确的 MIME/扩展名 reason，帮助模型选择下一步。
- 对 HTML 缓存命中结果暴露 `cache_status`，减少重复抓取。
- 支持条件刷新和用户显式强制刷新参数。
