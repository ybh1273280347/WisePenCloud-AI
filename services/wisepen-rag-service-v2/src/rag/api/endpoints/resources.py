"""将确定性 READ application 用例暴露为内部 HTTP endpoints。"""

from typing import Annotated

from common.core.domain import R
from common.core.exceptions import ServiceException
from common.security import SecurityContextHolder, require_login
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from rag.api.schemas import (
    ContentWindowResponse,
    DocumentStructureResponse,
    PageContentRequest,
    ResourceRequest,
    SectionContentRequest,
    SectionContentResponse,
)
from rag.application.rag.read import (
    ContentNotFoundError,
    DocumentContentReader,
    DocumentStructureReader,
)
from rag.container import Container
from rag.domain.acl import PermissionScope
from rag.domain.error_codes import RagErrorCode

router = APIRouter()

AuthenticatedUser = Annotated[str, Depends(require_login)]
StructureReader = Annotated[
    DocumentStructureReader,
    Depends(Provide[Container.document_structure_reader]),
]
ContentReader = Annotated[
    DocumentContentReader,
    Depends(Provide[Container.document_content_reader]),
]


@router.post("/document-structure", response_model=R[DocumentStructureResponse])
@inject
async def document_structure(
    request: ResourceRequest,
    user_id: AuthenticatedUser,
    reader: StructureReader,
) -> R[DocumentStructureResponse]:
    try:
        result = await reader.get(
            resource_id=request.resource_id,
            permission_scope=_permission_scope(user_id),
        )
    except ContentNotFoundError as error:
        raise ServiceException(RagErrorCode.RESOURCE_CONTENT_NOT_FOUND) from error
    except Exception as error:
        raise ServiceException(RagErrorCode.RESOURCE_READ_FAILED) from error
    revision = result.revision
    return R.success(
        DocumentStructureResponse(
            resource_id=revision.resource_id,
            document_version=revision.document_version,
            content_revision=revision.content_revision,
            structure_mode=revision.structure_mode.value,
            total_length=revision.total_length,
            pages=[
                {
                    "page_index": page.page_index,
                    "page_label": page.page_label,
                    "source_span": page.source_span,
                }
                for page in revision.pages
            ],
            sections=result.sections,
        )
    )


@router.post("/page-content", response_model=R[dict[str, ContentWindowResponse]])
@inject
async def page_content(
    request: PageContentRequest,
    user_id: AuthenticatedUser,
    reader: ContentReader,
) -> R[dict[str, ContentWindowResponse]]:
    try:
        result = await reader.get_pages(
            resource_id=request.resource_id,
            page_labels=request.page_labels,
            permission_scope=_permission_scope(user_id),
        )
    except ContentNotFoundError as error:
        raise ServiceException(RagErrorCode.RESOURCE_CONTENT_NOT_FOUND) from error
    except Exception as error:
        raise ServiceException(RagErrorCode.RESOURCE_READ_FAILED) from error
    return R.success(
        {
            key: ContentWindowResponse.model_validate(value, from_attributes=True)
            for key, value in result.items()
        }
    )


@router.post("/section-content", response_model=R[dict[str, SectionContentResponse]])
@inject
async def section_content(
    request: SectionContentRequest,
    user_id: AuthenticatedUser,
    reader: ContentReader,
) -> R[dict[str, SectionContentResponse]]:
    try:
        result = await reader.get_sections(
            resource_id=request.resource_id,
            section_ids=request.section_ids,
            permission_scope=_permission_scope(user_id),
        )
    except ContentNotFoundError as error:
        raise ServiceException(RagErrorCode.RESOURCE_CONTENT_NOT_FOUND) from error
    except Exception as error:
        raise ServiceException(RagErrorCode.RESOURCE_READ_FAILED) from error
    return R.success(
        {
            key: SectionContentResponse.model_validate(value, from_attributes=True)
            for key, value in result.items()
        }
    )


def _permission_scope(user_id: str) -> PermissionScope:
    return PermissionScope.from_group_roles(
        user_id,
        SecurityContextHolder.get_group_role_map(),
    )
