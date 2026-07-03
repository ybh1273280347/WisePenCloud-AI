# Utils 能力盘点

> 一句话：新增业务能力前，先来这里看看有没有现成入口。

本文只记录当前仓库已经沉淀的共享实现入口，方便快速定位“现成能力在哪里”。

规则、职责边界、开发流程判断放到 [03-shared-engines-and-dev-flow](03-shared-engines-and-dev-flow.md)。

## 目录边界

| 路径 | 定位 | 使用边界 |
| --- | --- | --- |
| `src/chat/application/utils/` | 应用层通用基础能力 | 不直接绑定某个 tool，可被多个应用服务或 tool 复用 |
| `src/chat/application/tools/utils/` | 工具层辅助能力 | 面向 tool 输入输出、文件识别、Markdown 渲染等工具侧需求 |

命名约定：

- 只有跨 tool、跨子包复用的稳定能力，才使用 `utils.py` 或 `utils/` 作为公开共享入口。
- 只服务于单个子包内部的辅助能力，应命名为 `_<子包标识>_utils.py` 或 `_<子包标识>_utils/`，例如 `_web_fetch_utils/`、`_search_provider_utils/`。
- 邻近子包确需临时复用内部能力时，也应通过带子包标识的私有路径引用，避免把它误认为通用工具层能力。

这里不重复写团队规则，只说明当前已有能力入口。

## Chunking Engine

路径：`src/chat/application/utils/chunking_engine/`

用途：把文本切成可读取、可检索、可定位的 chunks。

稳定入口：

- `ChunkingEngine`
- `ChunkDocument`
- `ChunkingPipeline`
- `ChunkingResult`
- `Chunk`
- `ChunkIndex`
- `UnitType`
- `IndexKind`

推荐 pipeline 在 `presets.py`：

| Pipeline | 适用场景 |
| --- | --- |
| `MARKDOWN_PIPELINE` | Markdown、网页正文、`document_parse` Markdown；默认首选 |
| `PLAIN_TEXT_PIPELINE` | 无结构纯文本 |
| `MARKDOWN_RECURSIVE_PIPELINE` | Markdown 很长且结构块过大，需要更均匀切分 |
| `NESTED_MARKDOWN_PIPELINE` | 需要父子块召回的 RAG 场景，当前不要默认使用 |

下游稳定入口：

- `chunk_index`
- `start_offset` / `end_offset`
- `metadata["unit_types"]`
- `metadata["section_paths"]`
- `metadata["page_label"]`
- `ChunkIndex.name`
- `ChunkIndex.kind`
- `ChunkIndex.chunk_indices`

## Ranking Engine

路径：`src/chat/application/utils/ranking_engine/`

用途：对业务候选做可解释排序。

稳定入口：

- `RankingEngine`
- `RankingPipeline`
- `RankRequest`
- `RankQuery`
- `RankCandidate`
- `RankResult`
- `RankedCandidate`
- `ScoreSignal`
- `TOOL_CONTENT_READ_RANKED_EXPAND_ENGINE`

现有组件：

| 子目录 | 能力 |
| --- | --- |
| `filters/` | `KeywordFilter` |
| `scorers/` | `BM25Scorer`、`FieldedBM25Scorer`、`PriorRankScorer`、`DenseVectorScorer` |
| `fusion/` | `WeightedRrfFusion`，当前默认推荐融合方式 |
| `rerankers/` | `ZeroEntropyReranker` |
| `diversifiers/` | `MmrDiversifier`、`GroupRoundRobinDiversifier`、`MaxMinDiversifier` |
| `text/` | `RankingTokenizer`、领域词典加载、停用词 |

接入时先把业务对象转成 `RankCandidate`，排序后再映射回业务对象。字段名应表达真实语义，例如 `section`、`anchor`、`title`、`snippet`，不要用 metadata 魔法 key 替代明确字段。

## LLM Clients

路径：`src/chat/application/utils/llm_clients/`

用途：提供轻量 LiteLLM query / embedding client，适合小范围内部任务复用。主聊天链路仍通过 `chat.core.providers.LiteLLMAdapter`。

现有入口：

- `LiteLLMQueryClient`
- `QueryResult`
- `query_client`
- `LiteLLMEmbeddingClient`
- `EmbeddingResult`
- `embedding_client`

## 文件类型识别

路径：`src/chat/application/tools/utils/file_type_detect.py`

用途：基于 Magika 识别本地文件类型，失败时回退到扩展名和 `mimetypes.guess_type`。

现有入口：

- `detect_file_type(file_path) -> FileType`
- `detect_mime_type(file_path) -> str`
- `FileType(label, mime_type)`

## URL 工具

路径：`src/chat/application/tools/utils/url/`

用途：工具层共享的 URL 能力。文件名提取、URL 抓取和 URL 安全校验分开放置，供 `web_fetch`、`web_crawl`、`document_parse` 直链下载和 `image_ocr` 图片 URL 读取复用。

现有入口：

- `filename.filename_from_url`
- `fetcher.fetch_url`
- `fetcher.FetchedUrl`
- `fetcher.UrlFetcherError` / `UrlFetcherNetworkError` / `UrlFetcherHttpError` / `UrlFetcherUnsupportedUrlError`
- `security.validate_public_http_url`
- `security.UrlSecurityError`

## Markdown 渲染器

路径：`src/chat/application/tools/utils/markdown_renderer/`

用途：把已确定的 HTML 片段按 HTML 语法树确定性渲染成适合模型阅读、缓存和分块的 Markdown。这里不处理特定业务或站点清洗逻辑，不做网页正文抽取、反爬判断、页面阻断、导航去噪或内容质量判断；这些策略属于具体工具自己的 cleaner。

现有入口：

- `html2markdown.HtmlToMarkdownRenderer`

### HtmlToMarkdownRenderer

将 HTML 片段直接转 Markdown，并可移除 `script`、`style`、`noscript`、`template`、`svg`、`canvas` 等语法树节点。它只做确定性的语法树到 Markdown 渲染，不调用 trafilatura 这类网页正文抽取器，也不承载 web page 专用清洗策略。

适用场景：OCR 或外部服务返回的局部 HTML 表格/片段。

## 快速定位

新增业务能力前先检查：

| 需求 | 用哪个能力 |
| --- | --- |
| 需要把大文本切块、生成章节/页码/锚点索引 | `chunking_engine` |
| 需要对候选排序、融合、多样性控制 | `ranking_engine` |
| 需要轻量调用模型或 embedding | `llm_clients` |
| 需要识别本地文件类型 | `detect_file_type` / `detect_mime_type` |
| 需要抓取 URL 并区分 HTML 与文件 | `tools/utils/url/fetcher.fetch_url` |
| 需要提取 URL 文件名 | `tools/utils/url/filename.filename_from_url` |
| 需要校验外部 URL 是否安全 | `tools/utils/url/security.validate_public_http_url` |
| 需要 HTML 片段转 Markdown | `markdown_renderer/html2markdown.HtmlToMarkdownRenderer` |
| 需要网页主体抽取成 Markdown | `web_tools/web_fetch/cleaners/TrafilaturaCleaner` |
| 需要复用外部 URL 抓取、HTML 清洗或文件解析结果 | `src/chat/application/tools/common/web_content_cache/`，不要混入 `ToolContentStore` |

## 文档入口

更细的组件说明见：

- `src/chat/application/utils/chunking_engine/README.md`
- `src/chat/application/utils/ranking_engine/README.md`
- `src/chat/application/utils/ranking_engine/ASSEMBLY_GUIDE.md`
- `docs/team/03-shared-engines-and-dev-flow.md`
