from fastapi import APIRouter

from rag.api.endpoints import resources_router

api_router = APIRouter()
api_router.include_router(resources_router, prefix="/resources", tags=["resources"])
