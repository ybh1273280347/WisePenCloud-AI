from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ToolSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # ── Timeouts (高频运维：超时控制) ─────────────────────────────────
    DOCUMENT_PARSE_TOOL_TIMEOUT_SECONDS: float = 300.0           # 文档解析工具单次执行超时
    WEB_SEARCH_TOOL_TIMEOUT_SECONDS: float = 300.0               # 网页搜索工具单次执行超时
    WEB_FETCH_TOOL_TIMEOUT_SECONDS: float = 300.0                # 网页抓取工具单次执行超时
    WEB_CRAWL_TOOL_TIMEOUT_SECONDS: float = 300.0                # 网页递归爬取工具单次执行超时
    TOOL_CONTENT_READ_TIMEOUT_SECONDS: float = 300.0             # 单个内容读取超时
    GET_HISTORICAL_CHAT_MESSAGES_TIMEOUT_SECONDS: float = 15.0   # 获取历史聊天记录超时
    CREATE_SKILL_TOOL_TIMEOUT_SECONDS: float = 15.0              # 创建技能工具超时
    LOAD_SKILL_TOOL_TIMEOUT_SECONDS: float = 20.0                # 加载技能工具超时
    LOAD_SKILL_ASSET_TOOL_TIMEOUT_SECONDS: float = 8.0           # 加载技能资产工具超时
    MATH_TOOL_TIMEOUT_SECONDS: float = 20.0                      # 数学计算工具超时
    RAG_KNOWLEDGE_SEARCH_TOOL_TIMEOUT_SECONDS: float = 300.0     # RAG 私有知识库检索工具超时

    WEB_SEARCH_TIMEOUT_SECONDS: float = 15.0                     # 网页搜索底层 API 超时
    WEB_FETCH_TIMEOUT_SECONDS: float = 30.0                      # 网页单页抓取超时
    PADDLE_OCR_TIMEOUT_SECONDS: float = 300.0                    # PaddleOCR 任务总超时
    PADDLE_OCR_POLL_HTTP_TIMEOUT: float = 30.0                   # PaddleOCR 单次轮询请求 HTTP 超时
    PADDLE_OCR_RESULT_HTTP_TIMEOUT: float = 60.0                 # PaddleOCR 结果 JSON 获取 HTTP 超时
    PDF_SANITIZE_TIMEOUT_SECONDS: float = 20.0                   # PDF 强制规范化超时

    # ── Concurrency & Batch (高频运维：并发与批量) ────────────────────
    DOCUMENT_PARSE_CONCURRENCY: int = 16                         # 文档解析并发数
    DOCUMENT_PARSE_MAX_FILE_REFS: int = 16                       # 单次文档解析最大服务批量
    DOCUMENT_PARSE_MAX_DOWNLOAD_BYTES: int = 52_428_800          # 文档解析直链下载最大字节数 (50 MiB)
    IMAGE_OCR_MAX_DOWNLOAD_BYTES: int = 52_428_800               # 图片 OCR 直链下载最大字节数 (50 MiB)

    WEB_FETCH_BATCH_CONCURRENCY: int = 16                        # 网页批量抓取并发数
    WEB_FETCH_SCRAPLING_CONCURRENCY: int = 3                     # Scrapling 慢路径并发数
    WEB_FETCH_MAX_SCRAPLING_FALLBACKS: int = 6                   # 单次 web_fetch 最多允许进入 Scrapling 的 URL 数
    TOOL_CONTENT_READ_MAX_CONTENT_IDS: int = 16                  # 单次读取最大内容 ID 数

    PADDLE_OCR_POLL_INTERVAL_SECONDS: float = 5.0                # PaddleOCR 轮询间隔
    PADDLE_OCR_MAX_POLL_ATTEMPTS: int = 60                       # PaddleOCR 最大轮询次数

    # ── Storage, Cache & GC (高频运维：仓储、缓存与清理) ────────────────
    CACHE_DEFAULT_TTL_SECONDS: int = 7200                        # URL 内容缓存默认过期时间 (2h)
    CACHE_MAX_TTL_SECONDS: int = 86400                           # URL 内容缓存过期上限时间 (24h)
    WEB_CONTENT_CACHE_CLEANUP_INTERVAL_SECONDS: int = 259_200    # Mongo 缓存 GC 扫描周期 (3d)
    WEB_CONTENT_CACHE_INACTIVE_RETENTION_SECONDS: int = 604_800  # inactive Mongo 缓存保留期 (7d)
    WEB_CONTENT_CACHE_CLEANUP_BATCH_SIZE: int = 1_000            # 单次 Mongo 缓存 GC 最大扫描文档数

    TOOL_CONTENT_DEFAULT_TTL_SECONDS: int = 1800                 # 工具内容缓存默认存活时间 (30min)
    TOOL_CONTENT_MAX_CHARS: int = 20_000_000                     # 工具内容允许的最大字符长度 (约 20M)

    TOOL_RUN_FILE_REF_TTL_SECONDS: int = 21_600                  # 运行时生成文件引用的默认 TTL (6h)
    TOOL_RUN_FILE_CLEANUP_GRACE_SECONDS: int = 600               # 后台 GC 清理过期文件的安全宽限期 (10min)
    TOOL_RUN_FILE_MAX_BYTES: int = 52_428_800                    # 运行时单文件允许的最大单资产大小 (50 MiB)

    # ── Web Search Behavior (网页搜索行为参数) ────────────────────────
    WEB_SEARCH_DEFAULT_RESULTS: int = 10                         # 网页搜索默认返回结果数
    WEB_SEARCH_MAX_RESULTS: int = 20                             # 网页搜索最大返回结果数
    WEB_SEARCH_MAX_RECOMMENDED_CANDIDATES: int = 5               # 最大推荐候选结果数
    WEB_SEARCH_FALLBACK_CANDIDATES_COUNT: int = 3                # 降级兜底候选结果数

    # ── Web Fetch & Crawl Behavior (网页抓取与爬取行为参数) ────────────
    WEB_FETCH_MAX_RESPONSE_BYTES: int = 52_428_800               # 网页抓取最大响应字节数 (50 MiB)
    WEB_FETCH_MIN_TEXT_LENGTH: int = 200                         # 网页抓取有效文本最小长度

    WEB_CRAWL_DEFAULT_MAX_PAGES: int = 20                        # 网页整站爬取默认最大页数
    WEB_CRAWL_MAX_MAX_PAGES: int = 100                           # 网页整站爬取上限最大页数
    WEB_CRAWL_DEFAULT_MAX_DEPTH: int = 2                         # 网页整站爬取默认最大深度
    WEB_CRAWL_MAX_MAX_DEPTH: int = 5                             # 网页整站爬取上限最大深度

    # ── Session & Content Read Behavior (会话与内容读取行为参数) ───────
    TOOL_CONTENT_READ_MAX_REGEX_PATTERN_CHARS: int = 500         # 内容读取正则模式最大字符数
    TOOL_CONTENT_READ_DEFAULT_MAX_MATCHES: int = 10              # 内容读取正则默认最大匹配数
    TOOL_CONTENT_READ_MAX_WINDOW_CHARS: int = 100_000            # 内容读取最大上下文窗口字符数

    # ── RAG Behavior (私有知识库检索行为参数) ─────────────────────────
    RAG_KNOWLEDGE_SEARCH_TOP_K: int = 8                         # RAG 证据条数
    RAG_KNOWLEDGE_SEARCH_CANDIDATE_LIMIT: int = 80              # RAG 候选召回数量
    RAG_KNOWLEDGE_SEARCH_ELASTIC_PREFILTER_LIMIT: int = 1000    # RAG Elastic 关键词过滤上限

    # ── Math Behavior (数学计算行为参数) ───────────────────────────────
    MATH_TOOL_MAX_EXPRESSION_CHARS: int = 2000                   # 数学表达式最大字符数


tool_settings = ToolSettings()
