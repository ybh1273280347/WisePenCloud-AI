from __future__ import annotations

from dataclasses import dataclass

from chat.application.tools.search_tools.web_search.core.sources import WebSearchSourceKind
from chat.application.tools.search_tools.web_search.providers.models import SearchProviderName


@dataclass(frozen=True, slots=True)
class WebSearchRuntimeConfig:
    """运行期固化的搜索配置上下文快照（ api_key 绝对隔离，不对模型可见）。"""
    user_id: str
    session_id: str
    search_config_id: str
    source_kind: WebSearchSourceKind
    provider: SearchProviderName | None
    source_id: str
    api_key: str | None = None
    credential_fingerprint: str | None = None
    credential_updated_at: str | None = None
    is_valid: bool = True
    error_message: str | None = None
