"""将 EXPAND 暴露为内部 HTTP endpoint。"""

from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from common.core.domain import R
from common.core.exceptions import ServiceException
from common.security import SecurityContextHolder, require_login
from rag.api.schemas import (
    EvidenceSource,
    GraphExpandRequest as ExpandHttpRequest,
    GraphExpandResponse,
    SectionExpandRequest,
    SectionExpandResponse,
)
from rag.application.rag.expand import (
    ExpandRequest,
    KnowledgeGraphExpander,
    SectionAccessRevokedError,
    SectionNotDiscoveredError,
    SectionRecordMissingError,
    SectionRevisionChangedError,
    SectionTreeExpander,
    UnknownSeedNodeError,
)
from rag.container import Container
from rag.domain.acl import PermissionScope
from rag.domain.error_codes import RagErrorCode
from rag.domain.evidence import EvidenceRevisionError
from rag.domain.navigation import NavigationStateNotFoundError

router = APIRouter()

AuthenticatedUser = Annotated[str, Depends(require_login)]
GraphExpander = Annotated[
    KnowledgeGraphExpander,
    Depends(Provide[Container.knowledge_graph_expander]),
]
TreeExpander = Annotated[
    SectionTreeExpander,
    Depends(Provide[Container.section_tree_expander]),
]


@router.post("/expand", response_model=R[GraphExpandResponse])
@inject
async def expand(
        request: ExpandHttpRequest,
        user_id: AuthenticatedUser,
        expander: GraphExpander,
) -> R[GraphExpandResponse]:
    try:
        result = await expander.expand(
            ExpandRequest(
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
            sources=[_evidence_source(record) for record in result.evidence],
        )
    )


@router.post("/expandSections", response_model=R[SectionExpandResponse])
@inject
async def expand_sections(
        request: SectionExpandRequest,
        user_id: AuthenticatedUser,
        expander: TreeExpander,
) -> R[SectionExpandResponse]:
    try:
        sections = await expander.expand(
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
        SectionExpandResponse.model_validate(
            {"state_id": request.state_id, "sections": sections}
        )
    )


def _permission_scope(user_id: str) -> PermissionScope:
    return PermissionScope.from_group_roles(
        user_id,
        SecurityContextHolder.get_group_role_map(),
    )


def _evidence_source(record) -> EvidenceSource:
    source_ref = record.source_ref
    return EvidenceSource(
        content=record.source_text,
        ref_id=source_ref.ref_id,
        resource_id=source_ref.resource_id,
        content_revision=source_ref.content_revision,
        chunk_id=source_ref.chunk_id,
        reading_block_id=source_ref.reading_block_id,
        section_id=source_ref.section_id,
        section_path=list(source_ref.section_path),
        source_spans=list(source_ref.source_spans),
        page_labels=list(source_ref.page_labels),
        anchor_labels=list(source_ref.anchor_labels),
    )
