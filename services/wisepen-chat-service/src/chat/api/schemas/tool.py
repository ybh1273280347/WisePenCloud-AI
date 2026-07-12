from typing import Any

from pydantic import BaseModel, Field


class ToolResponse(BaseModel):
    name: str
    description: str
    requires_config: bool
    configured: bool
    enabled: bool
    missing_config_keys: list[str] = Field(default_factory=list)
    config_schema: dict[str, Any] = Field(default_factory=dict)
    secret_fingerprints: dict[str, str] = Field(default_factory=dict)


class ListUserToolsResponse(BaseModel):
    tools: list[ToolResponse] = Field(default_factory=list)


class UpdateUserToolConfigRequest(BaseModel):
    tool_name: str
    enabled: bool | None = None
    config: dict[str, Any] | None = None
    secret_config: dict[str, str] | None = None


class DeleteUserToolConfigRequest(BaseModel):
    tool_name: str
