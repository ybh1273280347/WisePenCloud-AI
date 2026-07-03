from __future__ import annotations

from urllib.parse import urlparse

import httpx

from .models import (
    HydratedPaper,
    HydratedPaperAuthor,
    OpenAlexFailureReason,
)

OPENALEX_SEARCH_LIMIT = 2


class PaperHydrator:
    __slots__ = ("_base_url", "_client")

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient,
        base_url: str,
    ) -> None:
        self._client = http_client
        self._base_url = base_url.rstrip("/")

    async def hydrate(
        self,
        *,
        api_key: str | None = None,
        url: str | None = None,
        title: str | None = None,
    ) -> HydratedPaper:
        # 水合策略：URL 优先（精确匹配），URL 失败时回退到 title 模糊匹配
        if not api_key:
            return HydratedPaper(failure_reason=OpenAlexFailureReason.API_KEY_MISSING)
        try:
            if url:
                hydrated_by_url = await self._hydrate_by_url(url, api_key=api_key)
                # URL 水合成功或遇到限流时直接返回，不再尝试 title 路径
                if hydrated_by_url.failure_reason is None:
                    return hydrated_by_url
                if hydrated_by_url.failure_reason == OpenAlexFailureReason.RATE_LIMITED:
                    return hydrated_by_url
            if title:
                return await self._hydrate_by_title(title, api_key=api_key)
            # 既无 URL 也无 title，无法定位论文
            return HydratedPaper(failure_reason=OpenAlexFailureReason.MISSING_LOOKUP_KEY)
        except httpx.HTTPStatusError as exc:
            # 按 HTTP 状态码映射为语义化失败原因
            match exc.response.status_code:
                case 404:
                    return HydratedPaper(failure_reason=OpenAlexFailureReason.NOT_FOUND)
                case 429:
                    return HydratedPaper(failure_reason=OpenAlexFailureReason.RATE_LIMITED)
                case _:
                    return HydratedPaper(failure_reason=OpenAlexFailureReason.HTTP_ERROR)
        except httpx.HTTPError:
            # 网络层面的异常（超时、DNS 解析失败、连接拒绝等）
            return HydratedPaper(failure_reason=OpenAlexFailureReason.NETWORK_ERROR)

    async def _hydrate_by_url(self, url: str, *, api_key: str) -> HydratedPaper:
        # 标准化 URL 后，用 OpenAlex /works 端点搜索匹配的论文
        normalized_url = _normalize_url(url)
        if not normalized_url:
            return HydratedPaper(failure_reason=OpenAlexFailureReason.INVALID_URL)

        response = await self._client.get(
            f"{self._base_url}/works",
            params={
                "search": normalized_url,
                "per-page": OPENALEX_SEARCH_LIMIT,
                "api_key": api_key,
            },
        )
        response.raise_for_status()

        data = response.json()
        results = data.get("results") if isinstance(data, dict) else None
        if not results:
            return HydratedPaper(failure_reason=OpenAlexFailureReason.EMPTY_RESULTS)

        # 从返回结果中筛选 landing_page_url / oa_url 与搜索 URL 精确匹配的论文
        matched = [
            item
            for item in results
            if isinstance(item, dict) and _matched_work_url(item) == normalized_url
        ]
        if not matched:
            return HydratedPaper(failure_reason=OpenAlexFailureReason.URL_NOT_MATCHED)
        if len(matched) > 1:
            # 多条匹配意味着 URL 过于模糊，需人工判断
            return HydratedPaper(failure_reason=OpenAlexFailureReason.AMBIGUOUS_URL)
        return _paper_from_work(matched[0])

    async def _hydrate_by_title(self, title: str, *, api_key: str) -> HydratedPaper:
        # 标准化 title 后，用 OpenAlex /works 端点搜索，匹配 display_name / title
        normalized_title = _normalize_title(title)
        if not normalized_title:
            return HydratedPaper(failure_reason=OpenAlexFailureReason.EMPTY_TITLE)

        response = await self._client.get(
            f"{self._base_url}/works",
            params={
                "search": title,
                "per-page": OPENALEX_SEARCH_LIMIT,
                "api_key": api_key,
            },
        )
        response.raise_for_status()

        data = response.json()
        results = data.get("results") if isinstance(data, dict) else None
        if not results:
            return HydratedPaper(failure_reason=OpenAlexFailureReason.EMPTY_RESULTS)

        # 在搜索结果中精确匹配标题（标准化后比较）
        matched = [
            item
            for item in results
            if isinstance(item, dict)
            and _normalize_title(str(item.get("display_name") or item.get("title") or "")) == normalized_title
        ]
        if not matched:
            return HydratedPaper(failure_reason=OpenAlexFailureReason.TITLE_NOT_MATCHED)
        if len(matched) > 1:
            # 多条匹配意味着标题过于通用，无法唯一确定
            return HydratedPaper(failure_reason=OpenAlexFailureReason.AMBIGUOUS_TITLE)
        return _paper_from_work(matched[0])


def _paper_from_work(data: dict) -> HydratedPaper:
    # 将 OpenAlex work 响应映射为领域模型
    author_items: list[HydratedPaperAuthor] = []
    institution_names: list[str] = []
    for authorship in data.get("authorships") or ():
        author_name = authorship.get("author", {}).get("display_name")
        if not author_name:
            continue
        institutions = tuple(
            dict.fromkeys(
                institution.get("display_name")
                for institution in authorship.get("institutions") or ()
                if institution.get("display_name")
            )
        )
        institution_names.extend(institutions)
        author_items.append(HydratedPaperAuthor(name=author_name, institutions=institutions))

    return HydratedPaper(
        doi=data.get("doi"),
        publication_year=data.get("publication_year"),
        cited_by_count=data.get("cited_by_count"),
        authors=tuple(author_items),
        institutions=tuple(dict.fromkeys(institution_names)),
    )


def _normalize_title(value: str | None) -> str:
    # 统一标题格式：折叠空白、忽略大小写，方便后续精确比较
    if not value:
        return ""
    return " ".join(value.casefold().strip().split())


def _normalize_url(value: str | None) -> str | None:
    # 统一 URL 格式：小写 scheme + host，去掉尾部斜杠，方便后续精确比较
    if not value:
        return None
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    path = parsed.path.rstrip("/")
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}"


def _matched_work_url(data: dict) -> str | None:
    # 优先从 OpenAlex primary_location.landing_page_url 提取匹配 URL，其次回退到 open_access.oa_url
    primary_location = data.get("primary_location") or {}
    open_access = data.get("open_access") or {}
    return _normalize_url(primary_location.get("landing_page_url")) or _normalize_url(open_access.get("oa_url"))
