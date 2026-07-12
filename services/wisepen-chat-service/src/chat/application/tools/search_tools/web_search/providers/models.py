from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class SearchCapability:
    """搜索 provider 支持的检索模式。"""

    web: bool
    academic: bool


class SearchProviderName(StrEnum):
    """Web search provider 标识。"""

    EXA = "exa"
    TAVILY = "tavily"
    ANYSEARCH = "anysearch"
    BAIDU_QIANFAN = "baidu_qianfan"

    @property
    def capability(self) -> SearchCapability:
        if self == SearchProviderName.EXA:
            return SearchCapability(web=True, academic=True)
        return SearchCapability(web=True, academic=False)


class SearchMode(StrEnum):
    WEB = "web"
    ACADEMIC = "academic"


@dataclass(frozen=True, slots=True)
class ProviderSearchHttpRequest:
    """provider search request 的 HTTP 表达。"""

    method: str  # HTTP method
    path: str  # provider endpoint path
    params: dict[str, object] | None = None  # GET query 参数
    json: dict[str, object] | None = None  # POST JSON body


class ProviderSearchRequest:
    """provider 请求对象接口。"""

    def to_http_request(self) -> ProviderSearchHttpRequest:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class SearchPreview:
    """搜索结果的模型可见预览。"""

    overview: str | None = None  # provider 真实返回的摘要/简介/snippet
    highlights: tuple[str, ...] = ()  # provider 返回的高亮片段


@dataclass(frozen=True, slots=True)
class ProviderSearchResult:
    """模型最终消费的搜索结果。"""

    title: str  # 结果标题
    url: str  # 结果 URL，后续 web fetch 依赖该字段
    preview: SearchPreview = field(default_factory=SearchPreview)  # 模型可消费预览


@dataclass(frozen=True, slots=True)
class ProviderSearchResponse:
    """供应商搜索响应的归一化包装。"""

    query: str  # 本次查询文本
    provider: SearchProviderName | None  # 响应来源 provider；platform_default 不暴露内部 provider
    results: tuple[ProviderSearchResult, ...] = ()  # 模型最终消费的结果列表
    answer: str | None = None  # 供应商对整个 query 的直答，仅作为检索提示
    source_id: str | None = None  # 来源标识，区分平台内置源和用户自定义源
