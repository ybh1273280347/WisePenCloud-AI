from __future__ import annotations

from chat.application.tools.search_tools.base_search_tool import BaseSearchTool


class PlatformSearchTool(BaseSearchTool):
    def __init__(self, **kwargs):
        super().__init__(tool_name="platform_search", provider=None, **kwargs)
