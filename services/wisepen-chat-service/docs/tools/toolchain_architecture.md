# Toolchain Architecture

> 一句话：WisePen Chat Service 的工具体系由若干业务域工具组成，它们通过 URL、`tfile_*`、`cnt_*` 和 URL 缓存形成稳定协作链。

实现入口：`src/chat/application/tools`
注册入口：`src/chat/container.py`

## 已注册工具

| 分组 | 工具 |
| --- | --- |
| document | `document_parse`、`image_ocr` |
| math | `calculus_solve`、`linear_algebra_solve`、`equation_solve`、`stats_solve`、`expression_solve` |
| session | `tool_content_rerank_read`、`tool_content_regex_read`、`tool_content_sequential_read`、`get_historical_chat_messages` |
| search | `platform_search`、`exa_search`、`tavily_search`、`anysearch_search`、`baidu_qianfan_search` |
| web | `web_fetch`、`web_crawl` |
| skill | `load_skill`、`load_skill_asset` |
| rag | `rag_knowledge_search` |

## Runtime 信封

```text
ToolInvocation
  -> JsonSchemaCheck / RequiredContextCheck / custom preflight hooks
  -> tool.execute(...)
  -> ToolOutputRenderer
  -> ToolOutputCache
  -> RenderToolResult
```

工具可以返回普通结构，也可以返回 `ToolReturn`：

- `tag`：渲染成 XML 根节点。
- `visible_result`：直接给模型看的轻量结构化结果。
- `cacheable_texts`：大段正文、Markdown 或解析结果，交给 `ToolOutputCache` 生成 `cnt_*`。

## 三类引用

| 引用 | 生产者 | 消费者 | 语义 |
| --- | --- | --- | --- |
| `tfile_*` | `web_fetch`、`document_parse` 直链下载等 | `document_parse(file_refs=[...])`、`image_ocr(file_ref=...)` | 工具运行期临时文件引用，按 `user_id/session_id` 隔离。 |
| `cnt_*` | `ToolOutputCache` | `tool_content_rerank_read`、`tool_content_regex_read`、`tool_content_sequential_read` | 大文本缓存凭证，表示已有内容，不代表新外部抓取需求。 |

## 外界信息获取链

### 搜索证据链

```text
platform_search / exa_search / tavily_search / anysearch_search / baidu_qianfan_search
  -> candidate urls
  -> web_fetch(urls=[...])
  -> cleaned markdown
  -> cnt_*
  -> tool_content_rerank_read / tool_content_regex_read / tool_content_sequential_read
```

学术检索不再是独立工具；它是支持该能力的 provider 工具上的 `mode=academic`。

### 直达网页链

```text
web_fetch(urls=[...])
  -> cleaned markdown
  -> cnt_*
  -> session read tools
```

### 文件链

```text
document_parse(direct_urls=[...])
  -> file parse
  -> URL content cache + cnt_*
  -> session read tools

web_fetch(urls=[...])
  -> non-HTML file_ref tfile_*
  -> document_parse(file_refs=[...])
  -> parsed markdown
  -> URL content cache + cnt_*
```

## Web / Document 边界

- 明显的 PDF、Office、表格等文件直链，直接调用 `document_parse(direct_urls=[...])`。
- 明显图片 URL 需要精确抽字时调用 `image_ocr(file_path=...)`。
- 普通 HTML 页面或不确定类型 URL，调用 `web_fetch`。
- 多页站点采集，调用 `web_crawl`。
- 搜索工具只找候选，不能把 preview 或 supplier answer 当最终证据。

## 工具族流程

### Search 工具

```text
provider/platform search tool
  -> fixed provider/source
  -> SearchService.search(mode)
  -> visible candidates with URLs
  -> web_fetch
```

搜索工具不是默认暴露工具。每轮只根据当前用户 active 搜索凭证暴露一个入口：平台 active 暴露 `platform_search`，custom active 暴露对应 provider 工具，无 active 凭证则不暴露搜索工具。

### Web 工具

```text
web_fetch
  -> URL cache read
  -> httpx/scrapling
  -> HTML: cleaner -> URL cache -> cacheable_texts -> cnt_*
  -> non-HTML: URL cache stub -> tfile_* -> document_parse

web_crawl
  -> URL cache read per page
  -> httpx/scrapling
  -> cleaner -> URL cache -> cacheable_texts -> cnt_*
  -> raw_html link extraction for BFS
```

### Session 工具

```text
cnt_* receipt
  -> tool_content_rerank_read / tool_content_regex_read for cross-document retrieval
  -> tool_content_sequential_read for single-content continuation
```

## 模型约束

- 不要伪造 `tfile_*`、`cnt_*`、`skill_id`、asset path 或内部 URL。
- 不要把 search preview 或 supplier answer 当作正文证据。
- 不要把 obvious document file URL 包一层 `web_fetch`，直接给 `document_parse(direct_urls=[...])`。
- 不要把 `file_refs` 和 `direct_urls` 混在一次 document parse 调用里。
- 已有缓存凭证时先读缓存；只有用户明确要求刷新或现有证据不足时才重新获取。
- 不能从模型参数传入 `user_id`、`session_id`、API key、object key 或本地路径。

## 后续优化方向

- 给 provider search 工具补端到端回归：search -> fetch -> read。
- 给 `platform_search` 增加平台会员 provider 的配置可观测性。
- 持续调优 `web_fetch` / `document_parse` / `image_ocr` 提示词中的文件边界。
