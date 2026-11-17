from fastapi import APIRouter

from app.api.admin.router import router as admin_router
from app.api.agent.router import router as agent_router
from app.api.auth.router import router as auth_router
from app.api.draft.router import router as draft_router
from app.api.email.router import router as email_router
from app.api.gmail.router import router as gmail_router
from app.api.thread.router import router as thread_router

api_v1_router = APIRouter(prefix="/v1")
api_v1_router.include_router(auth_router)
api_v1_router.include_router(agent_router)
api_v1_router.include_router(email_router)
api_v1_router.include_router(thread_router)
api_v1_router.include_router(draft_router)
api_v1_router.include_router(admin_router)
api_v1_router.include_router(gmail_router)
