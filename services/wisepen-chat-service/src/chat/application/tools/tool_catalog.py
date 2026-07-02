from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolCatalogItem:
    """前端可展示的工具目录项。

    这是工具域内部模型，不是 API response。API 层需要自行做响应映射。
    """

    key: str
    label: str
    tool_names: tuple[str, ...]


# 这里只维护前端需要“看到”的目录项；模型实际可见工具仍由 ToolRegistry.derive() 决定。
TOOL_CATALOG_ITEMS = (
    ToolCatalogItem(
        key="web_search",
        label="联网搜索",
        # academic_search 归并在联网搜索目录项下；是否实际暴露由聊天链路静默处理。
        tool_names=("web_search", "academic_search"),
    ),
    ToolCatalogItem(
        key="math_tools",
        label="数学工具",
        tool_names=(
            "calculus_solver",
            "linear_algebra_solver",
            "equation_solver",
            "stats_solver",
            "expression_solver",
        ),
    ),
)


def list_tool_catalog_items() -> tuple[ToolCatalogItem, ...]:
    """返回前端工具目录的静态配置。"""

    return TOOL_CATALOG_ITEMS
