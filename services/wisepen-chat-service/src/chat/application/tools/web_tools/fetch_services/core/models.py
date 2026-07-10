from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class RawFetchOutput:
    """web_fetch 内部抓取结果：HTML 文本或非 HTML 临时文件路径。"""

    source_url: str
    fetcher: str
    status_code: int | None = None
    content_type: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    raw_html: str | None = None
    file_path: str | None = None
    file_label: str | None = None


@dataclass(frozen=True, slots=True)
class FetchQuality:
    """抓取质量判断结果，驱动 fallback 决策。

    仅承载决策语义：
    - should_fallback: 是否应触发降级链下一层
    - reason: 机器可读的判断原因（供日志使用）
    - text_length: 清洗后正文长度（供阈值判断与日志使用）
    """

    should_fallback: bool
    reason: str
    text_length: int


@dataclass(frozen=True, slots=True)
class WebFetchResult:
    """单页抓取成功结果。

    只承载对模型决策有用的语义字段：
    - source_url: 原始请求 URL，工具可见结果使用它标识来源
    - status_code / content_type: 内部缓存写入需要的 HTTP 元数据，不直接暴露给模型
    - title / markdown: HTML 页面路径的核心内容
    - file_ref / file_label: 非 HTML 文件发布后的统一文件引用
    - warnings: 会改变模型后续策略的提示，如最终正文质量不足

    两种互斥结果：
    - HTML 页面：title/markdown 有值，file_ref 为 None
    - 非 HTML 文件：file_ref/file_label 有值，title/markdown 为 None
    """

    source_url: str
    status_code: int | None
    content_type: str | None
    title: str | None
    markdown: str | None
    file_ref: str | None = None
    file_label: str | None = None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class WebFetchFailure:
    """单页抓取失败结果。

    只承载失败事实，不表达重试策略（重试语义由 ToolExecutionError 承载）：
    - url: 失败的目标 URL
    - reason: 机器可读失败原因
    """

    url: str
    reason: str


@dataclass(frozen=True, slots=True)
class WebFetchBatchResult:
    """批量抓取结果。

    只承载成功结果、失败理由，以及会影响后续策略的 warnings。
    """

    items: tuple[WebFetchResult, ...] = ()
    failed: tuple[WebFetchFailure, ...] = ()
    warnings: tuple[str, ...] = ()
