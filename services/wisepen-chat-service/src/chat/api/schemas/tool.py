from pydantic import BaseModel


class ToolListItem(BaseModel):
    """listTools 接口响应项。"""

    key: str
    label: str
    tool_names: list[str]


class ListToolsResponse(BaseModel):
    """listTools 接口响应体。"""

    tools: list[ToolListItem]
