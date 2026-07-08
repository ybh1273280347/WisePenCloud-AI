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

from chat.application.tools.core import ToolExecutionError
from chat.application.tools.search_tools.exa_search_tool import ExaSearchTool
from chat.application.tools.search_tools.platform_search_tool import PlatformSearchTool
from chat.application.tools.search_tools.web_search.core.runtime_context import WebSearchRuntimeConfig
from chat.application.tools.search_tools.web_search.core.sources import WebSearchSourceKind
from chat.application.tools.search_tools.web_search.pipeline.search_executor import WebSearchResult
from chat.application.tools.search_tools.web_search.providers.models import (
    ProviderSearchResponse,
    ProviderSearchResult,
    SearchMode,
    SearchPreview,
    SearchProviderName,
)


class FakeSearchService:
    def __init__(self, result: WebSearchResult) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    async def search(self, **kwargs) -> WebSearchResult:
        self.calls.append(kwargs)
        return self.result


class FakeCredentialRepository:
    def __init__(self, api_key: str = "exa-key") -> None:
        self.api_key = api_key
        self.calls: list[tuple[str, SearchProviderName]] = []

    async def get_custom_api_key(self, *, user_id: str, provider: SearchProviderName) -> str:
        self.calls.append((user_id, provider))
        return self.api_key


class FakeIntegrationSearcherFactory:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def build(self, **kwargs):
        self.calls.append(kwargs)
        return object()


class FakeRuntimeContextResolver:
    async def resolve_platform(self, *, user_id: str, session_id: str) -> WebSearchRuntimeConfig:
        return WebSearchRuntimeConfig(
            user_id=user_id,
            session_id=session_id,
            search_config_id="platform_member:exa",
            source_kind=WebSearchSourceKind.PLATFORM_MEMBER,
            provider=SearchProviderName.EXA,
            source_id="platform_member:exa",
            api_key="platform-key",
        )


class FakePlatformSourceFactory:
    def build(self, config: WebSearchRuntimeConfig):
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
async def test_exa_search_uses_provider_credential_and_academic_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _rank_candidates(**kwargs):
        return ["[1]"]

    monkeypatch.setattr(
        "chat.application.tools.search_tools.web_search.tool_utils.select_candidate_ids",
        _rank_candidates,
    )

    credential_repository = FakeCredentialRepository()
    integration_factory = FakeIntegrationSearcherFactory()
    service = FakeSearchService(_result())
    tool = ExaSearchTool(
        service=service,
        integration_searcher_factory=integration_factory,
        credential_repository=credential_repository,
    )

    result = await tool.execute(
        {"user_id": "user-1", "session_id": "session-1"},
        question="find rag papers",
        query="rag paper",
        mode="academic",
    )

    assert credential_repository.calls == [("user-1", SearchProviderName.EXA)]
    assert integration_factory.calls[0]["provider"] == SearchProviderName.EXA
    assert service.calls[0]["mode"] == SearchMode.ACADEMIC
    assert result.tag == "exa_search_result"
    assert result.visible_result["mode"] == "academic"
    assert result.visible_result["recommended_ids"] == ("[1]",)
    assert result.visible_result["candidates"][0].url == "https://arxiv.org/abs/1706.03762"


@pytest.mark.anyio
async def test_platform_search_resolves_platform_source_only(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _rank_candidates(**kwargs):
        return []

    monkeypatch.setattr(
        "chat.application.tools.search_tools.web_search.tool_utils.select_candidate_ids",
        _rank_candidates,
    )

    service = FakeSearchService(_result("platform query"))
    tool = PlatformSearchTool(
        service=service,
        platform_source_factory=FakePlatformSourceFactory(),
        runtime_context_resolver=FakeRuntimeContextResolver(),
    )

    result = await tool.execute(
        {"user_id": "user-1", "session_id": "session-1"},
        question="question",
        query="platform query",
    )

    assert service.calls[0]["source"].source_id == "platform_member:exa"
    assert service.calls[0]["mode"] == SearchMode.WEB
    assert result.tag == "platform_search_result"
    assert result.visible_result["mode"] == "web"
    assert result.visible_result["candidates"][0].url == "https://arxiv.org/abs/1706.03762"


@pytest.mark.anyio
async def test_platform_academic_mode_requires_academic_provider() -> None:
    class NonAcademicResolver:
        async def resolve_platform(self, *, user_id: str, session_id: str) -> WebSearchRuntimeConfig:
            return WebSearchRuntimeConfig(
                user_id=user_id,
                session_id=session_id,
                search_config_id="platform_default",
                source_kind=WebSearchSourceKind.PLATFORM_DEFAULT,
                provider=None,
                source_id="platform_default",
            )

    tool = PlatformSearchTool(
        service=FakeSearchService(_result()),
        platform_source_factory=FakePlatformSourceFactory(),
        runtime_context_resolver=NonAcademicResolver(),
    )

    with pytest.raises(ToolExecutionError) as exc_info:
        await tool.execute(
            {"user_id": "user-1", "session_id": "session-1"},
            question="papers",
            query="papers",
            mode="academic",
        )

    assert getattr(exc_info.value, "reason") == "platform_search_academic_unavailable"
