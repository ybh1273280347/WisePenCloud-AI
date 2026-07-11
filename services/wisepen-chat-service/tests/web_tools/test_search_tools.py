from __future__ import annotations

import sys
import types
from enum import StrEnum
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

common_module = types.ModuleType("common")
logger_module = types.ModuleType("common.logger")
core_module = types.ModuleType("common.core")
domain_module = types.ModuleType("common.core.domain")
exceptions_module = types.ModuleType("common.core.exceptions")
http_module = types.ModuleType("common.http")
rpc_client_module = types.ModuleType("common.http.rpc_client")


def _noop(*args, **kwargs):
    return None


class ServiceException(Exception):
    pass


class RpcError(Exception):
    pass


class RpcClient:
    pass


logger_module.error = _noop
logger_module.warn = _noop
logger_module.info = _noop
common_module.logger = logger_module
domain_module.GroupRoleType = object
exceptions_module.ServiceException = ServiceException
exceptions_module.RpcError = RpcError
rpc_client_module.RpcClient = RpcClient
sys.modules.setdefault("common", common_module)
sys.modules["common.logger"] = logger_module
sys.modules["common.core"] = core_module
sys.modules["common.core.domain"] = domain_module
sys.modules["common.core.exceptions"] = exceptions_module
sys.modules["common.http"] = http_module
sys.modules["common.http.rpc_client"] = rpc_client_module

llm_clients_module = types.ModuleType("chat.application.utils.llm_clients")


class _AdapterQueryClient:
    async def aquery(self, *args, **kwargs):
        raise AssertionError("test stub should not be called")


def _build_query_client():
    return _AdapterQueryClient()


llm_clients_module.AdapterQueryClient = _AdapterQueryClient
llm_clients_module.QueryClient = _AdapterQueryClient
llm_clients_module.build_query_client = _build_query_client
utils_module = types.ModuleType("chat.application.utils")
xml_markup_module = types.ModuleType("chat.application.utils.xml_markup")
xml_markup_module.xml_attr = lambda value: str(value)
xml_markup_module.xml_cdata = lambda value: str(value)
xml_markup_module.xml_text = lambda value: str(value)
utils_module.xml_markup = xml_markup_module
sys.modules["chat.application.utils"] = utils_module
sys.modules["chat.application.utils.llm_clients"] = llm_clients_module
sys.modules["chat.application.utils.xml_markup"] = xml_markup_module
sys.modules["jieba"] = types.ModuleType("jieba")

app_settings_module = types.ModuleType("chat.core.config.app_settings")
app_settings_module.settings = types.SimpleNamespace(QUERY_MODEL="test-query-model")
sys.modules["chat.core.config.app_settings"] = app_settings_module

beanie_module = types.ModuleType("beanie")


class _BeanieDocument:
    pass


beanie_module.Document = _BeanieDocument
beanie_module.PydanticObjectId = str
sys.modules["beanie"] = beanie_module

domain_entities_module = types.ModuleType("chat.domain.entities")
domain_entities_module.__path__ = []
domain_entities_module.ResourceItemInfo = object
domain_entities_module.ResourcePermission = object
web_search_credential_module = types.ModuleType("chat.domain.entities.web_search_credential")


class _WebSearchCredentialSource(StrEnum):
    PLATFORM_DEFAULT = "platform_default"
    PLATFORM_MEMBER = "platform_member"
    CUSTOM = "custom"


web_search_credential_module.WebSearchCredentialSource = _WebSearchCredentialSource
sys.modules["chat.domain.entities"] = domain_entities_module
sys.modules["chat.domain.entities.web_search_credential"] = web_search_credential_module

mongo_repo_module = types.ModuleType("chat.core.persistence.mongo.web_search_credential_repository")
mongo_repo_module.MongoWebSearchCredentialRepository = object
sys.modules["chat.core.persistence.mongo.web_search_credential_repository"] = mongo_repo_module

from chat.application.tools.search_tools.exa_search_tool import ExaSearchTool
from chat.application.tools.search_tools.platform_search_tool import PlatformSearchTool
from chat.application.tools.search_tools.web_search.core.runtime_context import WebSearchRuntimeConfig
from chat.application.tools.search_tools.web_search.core.sources import (
    PlatformDefaultSearchSource,
    WebSearchSourceKind,
)
from chat.application.tools.search_tools.web_search.pipeline.candidates_builder import build_candidates
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
