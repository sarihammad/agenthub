"""Main API router."""

from fastapi import APIRouter

from agenthub.api.v1 import admin, execute, plan, sessions, stream, tools

api_router = APIRouter()

# Include all v1 routers
api_router.include_router(sessions.router, prefix="/v1", tags=["sessions"])
api_router.include_router(plan.router, prefix="/v1", tags=["planning"])
api_router.include_router(execute.router, prefix="/v1", tags=["execution"])
api_router.include_router(stream.router, prefix="/v1", tags=["streaming"])
api_router.include_router(tools.router, prefix="/v1", tags=["tools"])
api_router.include_router(admin.router, prefix="/v1/admin", tags=["admin"])

