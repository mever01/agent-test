from fastapi import APIRouter
from app.api.v1.agent import router as agent_router
from app.api.v1.emails import router as emails_router
from app.api.v1.drafts import router as drafts_router
from app.api.v1.admin import router as admin_router

api_v1_router = APIRouter(prefix="/v1")
api_v1_router.include_router(agent_router)
api_v1_router.include_router(emails_router)
api_v1_router.include_router(drafts_router)
api_v1_router.include_router(admin_router)

__all__ = ["api_v1_router"]

