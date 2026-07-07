from __future__ import annotations

from pydantic import BaseModel

from chat.application.tools.web_tools.search_services.providers.models import SearchProviderName
from chat.domain.entities.web_search_credential import WebSearchCredentialSource


class CreateWebSearchCredentialRequest(BaseModel):
    provider: SearchProviderName
    source: WebSearchCredentialSource = WebSearchCredentialSource.CUSTOM
    api_key: str
    openalex_api_key: str | None = None


class WebSearchCredentialResponse(BaseModel):
    user_id: str
    provider: SearchProviderName | None
    source: WebSearchCredentialSource
    api_key_fingerprint: str
    support_academic: bool
    is_active: bool
    created_at: str
    updated_at: str


class SetActiveWebSearchCredentialRequest(BaseModel):
    source: WebSearchCredentialSource
    provider: SearchProviderName | None = None
