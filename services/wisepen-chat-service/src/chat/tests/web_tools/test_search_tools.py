from __future__ import annotations

import types

import pytest


from chat.application.tools.search_tools.exa_search_tool import ExaSearchTool
from chat.application.tools.search_tools.platform_search_tool import PlatformSearchTool
from chat.application.tools.search_tools.web_search.core.runtime_context import WebSearchRuntimeConfig
from chat.application.tools.search_tools.web_search.core.sources import (
    PlatformDefaultSearchSource,
    WebSearchSourceKind,
)
from chat.application.tools.search_tools.web_search.pipeline.candidates_builder import build_candidates
from chat.application.tools.search_tools.web_search.pipeline.candidate_selector import (
    _select_candidate_ids,
    select_recommended_ids,
)
from chat.application.tools.search_tools.web_search.pipeline.search_executor import WebSearchResult
from chat.application.tools.search_tools.web_search.providers.models import (
    ProviderSearchResponse,
    ProviderSearchResult,
    SearchMode,
    SearchPreview,
    SearchProviderName,
)
from chat.application.tools.search_tools.web_search.search_pipeline import SearchPipelineResult
from chat.application.tools.search_tools.web_search.searchers.base import BaseProviderSearcher
from chat.application.tools.search_tools.web_search.searchers.platform.default import PlatformDefaultSearcher


class FakeSearchPipeline:
    def __init__(self, result: WebSearchResult) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    async def search(self, **kwargs) -> SearchPipelineResult:
        self.calls.append(kwargs)
        candidates = build_candidates(self.result.responses)
        return SearchPipelineResult(
            search_result=self.result,
            candidates=candidates,
            recommended_ids=("[1]",),
        )


class FakeRuntimeContextResolver:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def resolve(
            self,
            *,
            user_id: str,
            provider: SearchProviderName | None,
    ) -> WebSearchRuntimeConfig:
        self.calls.append({"user_id": user_id, "provider": provider})
        return WebSearchRuntimeConfig(
            source_kind=(WebSearchSourceKind.PLATFORM_DEFAULT if provider is None else WebSearchSourceKind.CUSTOM),
            provider=provider,
            source_id="platform_default" if provider is None else f"custom:{provider.value}",
            api_key=None if provider is None else "custom-key",
        )


class FakeSearchSourceFactory:
    def __init__(self) -> None:
        self.calls: list[WebSearchRuntimeConfig] = []

    def build(self, config: WebSearchRuntimeConfig):
        self.calls.append(config)
        return types.SimpleNamespace(
            kind=config.source_kind,
            provider=config.provider,
            source_id=config.source_id,
            api_key=config.api_key,
            searcher=object(),
        )


def _result(query: str = "rag paper") -> WebSearchResult:
    return WebSearchResult(
        query=query,
        responses=(
            ProviderSearchResponse(
                query=query,
                provider=SearchProviderName.EXA,
                results=(
                    ProviderSearchResult(
                        title="Attention Is All You Need",
                        url="https://arxiv.org/abs/1706.03762",
                        preview=SearchPreview(
                            overview="overview",
                            highlights=("highlight",),
                        ),
                    ),
                ),
                source_id="custom:exa",
            ),
        ),
    )


@pytest.mark.anyio
async def test_exa_search_uses_unified_runtime_source_and_pipeline() -> None:
    resolver = FakeRuntimeContextResolver()
    source_factory = FakeSearchSourceFactory()
    pipeline = FakeSearchPipeline(_result())
    tool = ExaSearchTool(
        search_pipeline=pipeline,
        source_factory=source_factory,
        runtime_context_resolver=resolver,
    )

    result = await tool.execute(
        {"user_id": "user-1", "session_id": "session-1"},
        query="rag paper",
        mode="academic",
    )

    assert resolver.calls == [{"user_id": "user-1", "provider": SearchProviderName.EXA}]
    assert source_factory.calls[0].source_kind == WebSearchSourceKind.CUSTOM
    assert pipeline.calls[0]["mode"] == SearchMode.ACADEMIC
    assert result.tag == "exa_search_result"
    assert result.visible_result["mode"] == "academic"
    assert result.visible_result["recommended_ids"] == ("[1]",)
    assert result.visible_result["candidates"][0].url == "https://arxiv.org/abs/1706.03762"


@pytest.mark.anyio
async def test_platform_search_resolves_platform_source_only() -> None:
    resolver = FakeRuntimeContextResolver()
    source_factory = FakeSearchSourceFactory()
    pipeline = FakeSearchPipeline(_result("platform query"))
    tool = PlatformSearchTool(
        search_pipeline=pipeline,
        source_factory=source_factory,
        runtime_context_resolver=resolver,
    )

    result = await tool.execute(
        {"user_id": "user-1", "session_id": "session-1"},
        query="platform query",
    )

    assert resolver.calls == [{"user_id": "user-1", "provider": None}]
    assert source_factory.calls[0].source_kind == WebSearchSourceKind.PLATFORM_DEFAULT
    assert pipeline.calls[0]["mode"] == SearchMode.WEB
    assert result.tag == "platform_search_result"
    assert result.visible_result["mode"] == "web"
    assert result.visible_result["candidates"][0].url == "https://arxiv.org/abs/1706.03762"


@pytest.mark.anyio
async def test_platform_default_academic_search_falls_back_to_web() -> None:
    response = _result().responses[0]

    class Searcher:
        async def search_web(self, **kwargs):
            return response

    searcher = PlatformDefaultSearcher(
        fourget_searcher=Searcher(),
        ddg_searcher=Searcher(),
    )

    result = await searcher.search_academic(query="papers", max_results=10)

    assert result.source_id == "platform_default"


def test_platform_default_declares_web_only_capability() -> None:
    source = PlatformDefaultSearchSource(searcher=object())

    assert source.capability.web is True
    assert source.capability.academic is False


@pytest.mark.anyio
async def test_base_provider_academic_search_falls_back_to_web() -> None:
    response = _result().responses[0]

    class WebOnlySearcher(BaseProviderSearcher):
        def __init__(self) -> None:
            pass

        async def search_web(self, **kwargs):
            return response

    result = await WebOnlySearcher().search_academic(query="papers", max_results=10)

    assert result is response


@pytest.mark.anyio
async def test_candidate_selection_failure_falls_back_to_provider_order(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    class QuotaExceededClient:
        async def aquery(self, **kwargs):
            raise RuntimeError("query model quota exceeded")

    selected_ids = await _select_candidate_ids(
        search_query="rag paper",
        candidates_xml="<candidate id=\"[1]\"/>",
        client=QuotaExceededClient(),
    )
    assert selected_ids == []

    monkeypatch.setattr(
        "chat.application.tools.search_tools.web_search.pipeline.candidate_selector.build_query_client",
        lambda **kwargs: QuotaExceededClient(),
    )

    recommended_ids = await select_recommended_ids(
        search_query="rag paper",
        candidates=build_candidates(_result().responses),
        max_recommended_candidates=5,
        fallback_candidates_count=3,
    )

    assert recommended_ids == ("[1]",)
