from collections.abc import Awaitable, Callable

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

from app.agent.service import AgentService
from app.broker.rag.producer import RAGProducer
from app.db.models.user import User
from app.services.admin_service import AdminService
from app.services.auth_service import AuthService
from app.services.db_mail.draft import DraftService
from app.services.db_mail.raw_email import RawEmailService
from app.services.db_mail.thread import ThreadService
from app.services.rag.retrieval.email.service import EmailRetrievalService

from core.broker.client import RabbitMQClient


def get_email_retrieval_service(request: Request) -> EmailRetrievalService:
    return request.app.state.email_retrieval_service


def get_raw_email_service(request: Request) -> RawEmailService:
    return request.app.state.raw_email_service


def get_thread_service(request: Request) -> ThreadService:
    return request.app.state.thread_service


def get_draft_service(request: Request) -> DraftService:
    return request.app.state.draft_service


def get_rabbitmq_client(request: Request) -> RabbitMQClient:
    return request.app.state.rabbitmq_client


def get_rag_producer(request: Request) -> RAGProducer:
    return request.app.state.rag_producer


def get_agent_service(request: Request) -> AgentService:
    return request.app.state.agent_service


def get_admin_service(
    rag_producer: RAGProducer = Depends(get_rag_producer),
) -> AdminService:
    return AdminService(rag_producer=rag_producer)


bearer = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)


def get_auth_service(request: Request) -> AuthService:
    return request.app.state.auth_service


async def get_current_user(
    token: str | None = Depends(bearer),
    service: AuthService = Depends(get_auth_service),
) -> User:
    user = await service.authenticate(token) if token else None
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется действующий токен.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_role(allowed_roles: list[str]) -> Callable[..., Awaitable[User]]:
    async def check_role(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Доступ запрещён.")
        return user

    return check_role
