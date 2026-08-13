"""将 EXPAND 暴露为内部 HTTP endpoint。"""

from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from common.core.domain import R
from common.core.exceptions import ServiceException
from common.security import SecurityContextHolder, require_login
from rag.api.schemas import (
    DiscoveredSectionExpandRequest,
    DiscoveredSectionExpandResponse,
    GraphExpandRequest as ExpandHttpRequest,
    GraphExpandResponse,
)
from rag.application.rag.expand import (
    DiscoveredSectionExpander,
    GraphAccessRevokedError,
    GraphExpandRequest,
    KnowledgeGraphExpander,
    SectionAccessRevokedError,
    SectionNotDiscoveredError,
    SectionRecordMissingError,
    SectionRevisionChangedError,
    UnknownSeedNodeError,
)
from rag.application.rag.verify import EvidenceRevisionError
from rag.domain.models.acl import PermissionScope
from rag.domain.error_codes import RagErrorCode
from rag.domain.models.navigation import NavigationStateNotFoundError

router = APIRouter()

AuthenticatedUser = Annotated[str, Depends(require_login)]
GraphExpander = Annotated[
    KnowledgeGraphExpander,
    Depends(Provide["knowledge_graph_expander"]),
]
DiscoveredSectionsExpander = Annotated[
    DiscoveredSectionExpander,
    Depends(Provide["discovered_section_expander"]),
]


@router.post("/expandGraph", response_model=R[GraphExpandResponse])
@inject
async def expand_graph(
        request: ExpandHttpRequest,
        user_id: AuthenticatedUser,
        expander: GraphExpander,
) -> R[GraphExpandResponse]:
    try:
        result = await expander.expand(
            GraphExpandRequest(
                state_id=request.state_id,
                session_id=request.session_id,
                permission_scope=_permission_scope(user_id),
                seed_node_ids=request.seed_node_ids,
                relation_types=request.relation_types,
                direction=request.direction,
                max_depth=request.max_depth,
                max_results=request.max_results,
                query=request.query,
            )
        )
    except NavigationStateNotFoundError as error:
        raise ServiceException(RagErrorCode.NAVIGATION_STATE_NOT_FOUND) from error
    except EvidenceRevisionError as error:
        raise ServiceException(RagErrorCode.NAVIGATION_STATE_INVALIDATED) from error
    except GraphAccessRevokedError as error:
        raise ServiceException(RagErrorCode.NAVIGATION_STATE_INVALIDATED) from error
    except (UnknownSeedNodeError, ValueError) as error:
        raise ServiceException(RagErrorCode.NAVIGATION_INVALID) from error
    except Exception as error:
        raise ServiceException(RagErrorCode.NAVIGATION_FAILED) from error
    return R.success(
        GraphExpandResponse(
            state_id=result.state_id,
            nodes=result.nodes,
            edges=result.edges,
            paths=result.paths,
            sources=result.sources,
        )
    )


@router.post(
    "/expandDiscoveredSections",
    response_model=R[DiscoveredSectionExpandResponse],
    summary="展开当前 navigation state 已发现的 Section",
    description=(
        "只能读取 state.known_sections 中已经发现的 section，并在读取后把相邻标题入口写回 state；"
        "如果调用方只是从 document structure 选择标题正文，应使用 read/getSectionContent。"
    ),
)
@inject
async def expand_discovered_sections(
        request: DiscoveredSectionExpandRequest,
        user_id: AuthenticatedUser,
        expander: DiscoveredSectionsExpander,
) -> R[DiscoveredSectionExpandResponse]:
    try:
        result = await expander.expand(
            state_id=request.state_id,
            session_id=request.session_id,
            permission_scope=_permission_scope(user_id),
            section_ids=request.section_ids,
        )
    except NavigationStateNotFoundError as error:
        raise ServiceException(RagErrorCode.NAVIGATION_STATE_NOT_FOUND) from error
    except SectionNotDiscoveredError as error:
        raise ServiceException(RagErrorCode.NAVIGATION_INVALID) from error
    except (
            SectionAccessRevokedError,
            SectionRecordMissingError,
            SectionRevisionChangedError,
    ) as error:
        raise ServiceException(RagErrorCode.NAVIGATION_STATE_INVALIDATED) from error
    except Exception as error:
        raise ServiceException(RagErrorCode.NAVIGATION_FAILED) from error
    return R.success(
        DiscoveredSectionExpandResponse.model_validate(result)
    )


def _permission_scope(user_id: str) -> PermissionScope:
    return PermissionScope.from_group_roles(
        user_id,
        SecurityContextHolder.get_group_role_map(),
    )
