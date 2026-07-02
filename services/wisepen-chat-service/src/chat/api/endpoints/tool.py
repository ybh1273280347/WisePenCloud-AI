from __future__ import annotations

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from chat.api.schemas.tool import ListToolsResponse, ToolListItem
from chat.application.tools.tool_catalog import list_tool_catalog_items
from chat.container import Container
from chat.domain.repositories import SessionRepository
from common.core.domain import R
from common.security import require_login

router = APIRouter()


@router.get("/listTools", response_model=R[ListToolsResponse])
@inject
async def list_tools(
        session_id: str,
        user_id: str = Depends(require_login),
        session_repo: SessionRepository = Depends(Provide[Container.session_repo]),
):
    # listTools 只服务前端展示；真实 tool 可见性仍由聊天链路的 ToolRegistry scope 决定。
    await session_repo.get_session_for_user(session_id, user_id)

    # API 层只负责把工具目录项映射成接口响应，不在这里维护目录配置本身。
    return R.success(data=ListToolsResponse(
        tools=[
            ToolListItem(
                key=item.key,
                label=item.label,
                tool_names=list(item.tool_names),
            )
            for item in list_tool_catalog_items()
        ],
    ))
