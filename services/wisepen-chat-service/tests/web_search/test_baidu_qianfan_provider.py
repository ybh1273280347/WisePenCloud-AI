from __future__ import annotations

import sys
import types
from enum import StrEnum
from pathlib import Path

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


logger_module.error = _noop
logger_module.warn = _noop
logger_module.info = _noop
common_module.logger = logger_module
domain_module.GroupRoleType = object
exceptions_module.RpcError = Exception
rpc_client_module.RpcClient = object
sys.modules.setdefault("common", common_module)
sys.modules["common.logger"] = logger_module
sys.modules["common.core"] = core_module
sys.modules["common.core.domain"] = domain_module
sys.modules["common.core.exceptions"] = exceptions_module
sys.modules["common.http"] = http_module
sys.modules["common.http.rpc_client"] = rpc_client_module

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

from chat.application.tools.search_tools.web_search.providers.baidu_qianfan import (
    BaiduQianfanSearchRequest,
    map_baidu_qianfan_response,
)
from chat.application.tools.search_tools.web_search.providers.models import SearchProviderName
from chat.application.tools.search_tools.web_search.core.runtime_context import WebSearchRuntimeConfig
from chat.application.tools.search_tools.web_search.core.sources import WebSearchSourceKind
from chat.application.tools.search_tools.web_search.factories.search_source_factory import (
    SearchSourceFactory,
)
from chat.application.tools.search_tools.web_search.searchers import BaiduQianfanSearcher


class _FakeHttpClient:
    pass


def test_baidu_qianfan_request_maps_to_ai_search_web_endpoint() -> None:
    request = BaiduQianfanSearchRequest(
        query="百度千帆 AI 搜索",
        max_results=3,
    ).to_http_request()

    assert request.method == "POST"
    assert request.path == "/v2/ai_search/web_search"
    assert request.json == {
        "messages": [
            {
                "role": "user",
                "content": "百度千帆 AI 搜索",
            }
        ],
        "search_source": "baidu_search_v2",
        "resource_type_filter": [
            {
                "type": "web",
                "top_k": 3,
            }
        ],
    }


def test_baidu_qianfan_response_maps_web_references_only() -> None:
    response = map_baidu_qianfan_response(
        {
            "answer": "供应商直答",
            "references": [
                {
                    "type": "web",
                    "title": "千帆 API 文档",
                    "url": "https://cloud.baidu.com/doc/qianfan-api/s/Wmbq4z7e5",
                    "content": "AI 搜索接口说明",
                },
                {
                    "type": "image",
                    "title": "图片结果",
                    "url": "https://example.com/image",
                    "content": "不应进入网页候选",
                },
                {
                    "title": "未标类型网页",
                    "url": "https://example.com/page",
                    "snippet": "兼容未返回 type 的结果",
                },
                {
                    "type": "web",
                    "title": "重复 URL",
                    "url": "https://example.com/page",
                    "content": "应按 URL 去重",
                },
            ],
        },
        query="千帆搜索",
        max_results=10,
    )

    assert response.provider == SearchProviderName.BAIDU_QIANFAN
    assert response.answer == "供应商直答"
    assert [item.title for item in response.results] == [
        "千帆 API 文档",
        "未标类型网页",
    ]
    assert response.results[0].preview.overview == "AI 搜索接口说明"
    assert response.results[1].preview.overview == "兼容未返回 type 的结果"


def test_search_source_factory_builds_baidu_qianfan_searcher() -> None:
    factory = SearchSourceFactory(
        http_client=_FakeHttpClient(),
        platform_default_searcher=object(),
        exa_base_url="https://api.exa.ai",
        tavily_base_url="https://api.tavily.com",
        anysearch_base_url="https://api.anysearch.com",
        baidu_qianfan_base_url="https://qianfan.baidubce.com",
    )

    source = factory.build(WebSearchRuntimeConfig(
        source_kind=WebSearchSourceKind.CUSTOM,
        provider=SearchProviderName.BAIDU_QIANFAN,
        api_key="qianfan-key",
        source_id="custom:baidu_qianfan:test",
    ))

    assert isinstance(source.searcher, BaiduQianfanSearcher)
