"""将资源结构和正文读取暴露为内部 HTTP endpoints。"""

from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from common.core.domain import R
from common.core.exceptions import ServiceException
from common.security import SecurityContextHolder, require_login
from rag.api.schemas import (
    DocumentStructureResponse,
    PageContentRequest,
    ResourceRequest,
    SectionContentRequest,
)
from rag.application.rag.read import (
    ContentAccessRevokedError,
    ContentNotFoundError,
    DocumentContentReader,
    DocumentStructureReader,
)
from rag.domain.models.acl import PermissionScope
from rag.domain.error_codes import RagErrorCode
from rag.domain.models.content import ContentWindow, SectionContent

router = APIRouter()

AuthenticatedUser = Annotated[str, Depends(require_login)]
StructureReader = Annotated[
    DocumentStructureReader,
    Depends(Provide["document_structure_reader"]),
]
ContentReader = Annotated[
    DocumentContentReader,
    Depends(Provide["document_content_reader"]),
]


@router.post("/getDocumentStructure", response_model=R[DocumentStructureResponse])
@inject
async def get_document_structure(
        request: ResourceRequest,
        user_id: AuthenticatedUser,
        reader: StructureReader,
) -> R[DocumentStructureResponse]:
    try:
        result = await reader.get_structure(
            resource_id=request.resource_id,
            permission_scope=_permission_scope(user_id),
        )
    except ContentNotFoundError as error:
        raise ServiceException(RagErrorCode.RESOURCE_CONTENT_NOT_FOUND) from error
    except ContentAccessRevokedError as error:
        raise ServiceException(RagErrorCode.RESOURCE_READ_FAILED) from error
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
            pages=revision.pages,
            sections=result.sections,
            section_tree=result.section_tree,
        )
    )


@router.post("/getPageContent", response_model=R[dict[str, ContentWindow]])
@inject
async def get_page_content(
        request: PageContentRequest,
        user_id: AuthenticatedUser,
        reader: ContentReader,
) -> R[dict[str, ContentWindow]]:
    try:
        result = await reader.get_pages(
            resource_id=request.resource_id,
            page_labels=request.page_labels,
            permission_scope=_permission_scope(user_id),
        )
    except ContentNotFoundError as error:
        raise ServiceException(RagErrorCode.RESOURCE_CONTENT_NOT_FOUND) from error
    except ContentAccessRevokedError as error:
        raise ServiceException(RagErrorCode.RESOURCE_READ_FAILED) from error
    except Exception as error:
        raise ServiceException(RagErrorCode.RESOURCE_READ_FAILED) from error
    return R.success(result)


@router.post("/getSectionContent", response_model=R[dict[str, SectionContent]])
@inject
async def get_section_content(
        request: SectionContentRequest,
        user_id: AuthenticatedUser,
        reader: ContentReader,
) -> R[dict[str, SectionContent]]:
    try:
        result = await reader.get_sections(
            resource_id=request.resource_id,
            section_ids=request.section_ids,
            permission_scope=_permission_scope(user_id),
        )
    except ContentNotFoundError as error:
        raise ServiceException(RagErrorCode.RESOURCE_CONTENT_NOT_FOUND) from error
    except ContentAccessRevokedError as error:
        raise ServiceException(RagErrorCode.RESOURCE_READ_FAILED) from error
    except Exception as error:
        raise ServiceException(RagErrorCode.RESOURCE_READ_FAILED) from error
    return R.success(result)


def _permission_scope(user_id: str) -> PermissionScope:
    return PermissionScope.from_group_roles(
        user_id,
        SecurityContextHolder.get_group_role_map(),
    )
