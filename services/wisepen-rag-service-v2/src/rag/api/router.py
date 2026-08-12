from fastapi import APIRouter

from rag.api.endpoints import expand_router, locate_router, read_router

api_router = APIRouter()
api_router.include_router(
    locate_router,
    tags=["locate"],
)
api_router.include_router(read_router, tags=["read"])
api_router.include_router(expand_router, tags=["expand"])
