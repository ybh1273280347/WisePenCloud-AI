from __future__ import annotations

import sys
import types
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

common_module = types.ModuleType("common")
logger_module = types.ModuleType("common.logger")


def _noop(*args, **kwargs):
    return None


logger_module.error = _noop
logger_module.warn = _noop
logger_module.info = _noop
common_module.logger = logger_module
sys.modules.setdefault("common", common_module)
sys.modules["common.logger"] = logger_module

llm_clients_module = types.ModuleType("chat.application.utils.llm_clients")


class _AdapterQueryClient:
    async def aquery(self, *args, **kwargs):
        raise AssertionError("test stub should not be called")


def _build_query_client():
    return _AdapterQueryClient()


llm_clients_module.AdapterQueryClient = _AdapterQueryClient
llm_clients_module.QueryClient = _AdapterQueryClient
llm_clients_module.build_query_client = _build_query_client
sys.modules["chat.application.utils.llm_clients"] = llm_clients_module
sys.modules["jieba"] = types.ModuleType("jieba")

app_settings_module = types.ModuleType("chat.core.config.app_settings")
app_settings_module.settings = SimpleNamespace(QUERY_MODEL="test-query-model")
sys.modules["chat.core.config.app_settings"] = app_settings_module

beanie_module = types.ModuleType("beanie")


class _BeanieDocument:
    pass


beanie_module.Document = _BeanieDocument
beanie_module.PydanticObjectId = str
sys.modules["beanie"] = beanie_module

domain_entities_module = types.ModuleType("chat.domain.entities")
domain_entities_module.__path__ = []
web_search_credential_module = types.ModuleType("chat.domain.entities.web_search_credential")


class _WebSearchCredentialSource(StrEnum):
    PLATFORM = "platform"
    CUSTOM = "custom"


web_search_credential_module.WebSearchCredentialSource = _WebSearchCredentialSource
sys.modules["chat.domain.entities"] = domain_entities_module
sys.modules["chat.domain.entities.web_search_credential"] = web_search_credential_module

from chat.application.tools.web_tools.academic_search_tool import AcademicSearchTool
from chat.application.tools.core import ToolExecutionError
from chat.application.tools.web_tools.search_services.errors import WebSearchEmptyResult
from chat.application.tools.web_tools.search_services.providers.models import (
    ProviderSearchResponse,
    ProviderSearchResult,
    SearchPreview,
    SearchProviderName,
)
from chat.application.tools.web_tools.search_services.runtime_context import (
    WebSearchMode,
    WebSearchRuntimeConfig,
)
from chat.application.tools.web_tools.search_services.services.academic_search.hydrators import (
    HydratedPaper,
    HydratedPaperAuthor,
)
from chat.application.tools.web_tools.search_services.services.academic_search.service import (
    AcademicSearchService,
)
from chat.application.tools.web_tools.search_services.services.search import WebSearchResult
from chat.application.tools.web_tools.web_search_tool import WebSearchTool


@dataclass
class FakeCandidateRepository:
    mappings: list[object]

    async def set_mapping(self, mapping, *, ttl_seconds: int) -> None:
        self.mappings.append(mapping)

    async def get_mapping(self, *, user_id: str, search_ref: str):
        raise NotImplementedError

    async def delete_mapping(self, *, user_id: str, search_ref: str) -> None:
        raise NotImplementedError


class FakeWebSearchService:
    def __init__(self, responses: list[WebSearchResult]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    async def search(
        self,
        *,
        query: str,
        max_results: int = 10,
        custom_source=None,
        platform_provider: SearchProviderName = SearchProviderName.FOUGET_DDG,
    ) -> WebSearchResult:
        self.calls.append((query, "web"))
        result = self._responses.pop(0)
        if not any(response.results for response in result.responses):
            raise WebSearchEmptyResult(
                provider=platform_provider if custom_source is None else custom_source.provider,
                reason="搜索源成功响应但没有返回结果",
            )
        return result

    async def search_academic(
        self,
        *,
        query: str,
        max_results: int = 10,
        custom_source=None,
        platform_provider: SearchProviderName = SearchProviderName.FOUGET_DDG,
    ) -> WebSearchResult:
        self.calls.append((query, "academic"))
        result = self._responses.pop(0)
        if not any(response.results for response in result.responses):
            raise WebSearchEmptyResult(
                provider=platform_provider if custom_source is None else custom_source.provider,
                reason="搜索源成功响应但没有返回结果",
            )
        return result


class FakeCustomSourceFactory:
    def __init__(self, *, searcher=None):
        self.searcher = searcher

    def build(self, config):
        return SimpleNamespace(
            provider=config.provider,
            api_key=config.api_key,
            searcher=self.searcher,
        )


class FakePaperHydrator:
    def __init__(self, result: HydratedPaper) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    async def hydrate(self, **kwargs) -> HydratedPaper:
        self.calls.append(kwargs)
        return self.result


class FakeProviderSearcher:
    def __init__(self, responses: list[WebSearchResult]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    async def search_web(
        self,
        *,
        query: str,
        max_results: int,
    ) -> ProviderSearchResponse:
        self.calls.append((query, "web"))
        return self._responses.pop(0).responses[0]

    async def search_academic(
        self,
        *,
        query: str,
        max_results: int,
    ) -> ProviderSearchResponse:
        self.calls.append((query, "academic"))
        return self._responses.pop(0).responses[0]


def _response(
    *,
    query: str,
    url: str | None = None,
    title: str = "Sample Title",
    source_id: str = "custom:exa:test",
) -> WebSearchResult:
    results = ()
    if url is not None:
        results = (
            ProviderSearchResult(
                title=title,
                url=url,
                preview=SearchPreview(
                    overview="overview",
                    highlights=("highlight",),
                ),
            ),
        )
    return WebSearchResult(
        query=query,
        responses=(
            ProviderSearchResponse(
                query=query,
                provider=SearchProviderName.EXA,
                results=results,
                source_id=source_id,
            ),
        ),
    )


@pytest.mark.anyio
async def test_web_search_empty_result_does_not_run_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _rank_candidates(**kwargs):
        return []

    monkeypatch.setattr(
        "chat.application.tools.web_tools._search_tool_utils.rank_candidate_ids",
        _rank_candidates,
    )

    service = FakeWebSearchService(
        responses=[
            _response(query="first", url=None),
        ]
    )
    repository = FakeCandidateRepository(mappings=[])
    tool = WebSearchTool(
        service=service,
        custom_source_factory=FakeCustomSourceFactory(),
        candidate_repository=repository,
    )
    with pytest.raises(ToolExecutionError) as exc_info:
        await tool.execute(
            {
                "user_id": "user-1",
                "session_id": "session-1",
                "search_config": WebSearchRuntimeConfig(
                    user_id="user-1",
                    session_id="session-1",
                    search_config_id="platform:4get_ddg",
                    search_mode=WebSearchMode.PLATFORM,
                    provider=SearchProviderName.FOUGET_DDG,
                    source_id="platform:4get_ddg",
                ),
            },
            question="question",
            query="first",
        )

    assert getattr(exc_info.value, "reason") == "web_search_empty_result"
    assert service.calls == [("first", "web")]
    assert repository.mappings == []


@pytest.mark.anyio
async def test_academic_search_keeps_exa_url_after_openalex_hydration(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _rank_candidates(**kwargs):
        return []

    monkeypatch.setattr(
        "chat.application.tools.web_tools._search_tool_utils.rank_candidate_ids",
        _rank_candidates,
    )

    repository = FakeCandidateRepository(mappings=[])
    provider_searcher = FakeProviderSearcher(
        responses=[
            WebSearchResult(
                query="rag paper",
                responses=(
                    ProviderSearchResponse(
                        query="rag paper",
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
                        source_id="custom:exa:test",
                    ),
                ),
            ),
        ]
    )
    hydrator = FakePaperHydrator(
        HydratedPaper(
            doi="10.1000/test",
            publication_year=2020,
            cited_by_count=42,
            authors=(
                HydratedPaperAuthor(
                    name="Patrick Lewis",
                    institutions=("Meta AI",),
                ),
            ),
            institutions=("Meta AI",),
        )
    )
    academic_service = AcademicSearchService(
        platform_searchers={},
        paper_hydrator=hydrator,
    )
    tool = AcademicSearchTool(
        service=academic_service,
        custom_source_factory=FakeCustomSourceFactory(searcher=provider_searcher),
        candidate_repository=repository,
    )

    result = await tool.execute(
        {
            "user_id": "user-1",
            "session_id": "session-1",
            "search_config": WebSearchRuntimeConfig(
                user_id="user-1",
                session_id="session-1",
                search_config_id="custom:exa",
                search_mode=WebSearchMode.CUSTOM,
                provider=SearchProviderName.EXA,
                source_id="custom:exa:test",
                api_key="exa-key",
                openalex_api_key="openalex-key",
                supports_academic=True,
            ),
        },
        question="find rag papers",
        query="rag paper",
    )

    candidate = result.visible_result["candidates"][0]
    assert result.visible_result["query"] == "rag paper"
    assert provider_searcher.calls == [("rag paper", "academic")]
    assert not hasattr(candidate, "url")
    assert not hasattr(candidate, "final_url_source")
    assert not hasattr(candidate, "open_access")
    assert candidate.doi == "10.1000/test"
    assert repository.mappings[0].url == "https://arxiv.org/abs/1706.03762"
