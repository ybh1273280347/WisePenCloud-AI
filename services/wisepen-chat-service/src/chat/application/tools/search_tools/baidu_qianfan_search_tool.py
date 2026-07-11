from __future__ import annotations

from chat.application.tools.search_tools.base_search_tool import BaseSearchTool
from chat.application.tools.search_tools.web_search.providers.models import SearchProviderName


class BaiduQianfanSearchTool(BaseSearchTool):
    def __init__(self, **kwargs):
        super().__init__(tool_name="baidu_qianfan_search", provider=SearchProviderName.BAIDU_QIANFAN, **kwargs)

