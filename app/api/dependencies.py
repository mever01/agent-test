from collections.abc import Awaitable, Callable

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

from app.db.models.user import User
from app.services.auth_service import AuthService

from app.broker.rag.producer import RAGProducer
from app.db.repositories.mail_repository import MailRepository
from app.db.repositories.rag_document_repository import RAGDocumentRepository
from app.db.repositories.rag_thread_repository import RAGThreadRepository
from app.db.session import AsyncSessionLocal
from app.services.admin_service import AdminService
from core.broker.client import RabbitMQClient
from app.agent.service import AgentService
from app.services.mail_service import MailService


def get_mail_repo() -> MailRepository:
    return MailRepository(AsyncSessionLocal)


def get_rag_document_repo() -> RAGDocumentRepository:
    return RAGDocumentRepository(AsyncSessionLocal)


def get_rag_thread_repo() -> RAGThreadRepository:
    return RAGThreadRepository(AsyncSessionLocal)


def get_rabbitmq_client(request: Request) -> RabbitMQClient:
    return request.app.state.rabbitmq_client


def get_rag_producer(request: Request) -> RAGProducer:
    return request.app.state.rag_producer


def get_mail_service(
    mail_repo: MailRepository = Depends(get_mail_repo),
    rag_producer: RAGProducer = Depends(get_rag_producer),
) -> MailService:
    return MailService(mail_repo=mail_repo, rag_producer=rag_producer)


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
