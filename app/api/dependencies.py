from typing import AsyncGenerator
from fastapi import Header, HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.db.repositories.email_repository import EmailRepository
from app.db.repositories.vector_repository import VectorRepository
from app.external_api_clients.embedding_client import EmbeddingClient
from app.external_api_clients.llm_client import LLMClient
from app.rag.retrieval import RAGRetrievalService
from app.queue.publisher import EventPublisher

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session

def get_email_repo(session: AsyncSession = Depends(get_db)) -> EmailRepository:
    return EmailRepository(session)

def get_vector_repo(session: AsyncSession = Depends(get_db)) -> VectorRepository:
    return VectorRepository(session)

def get_embedding_client() -> EmbeddingClient:
    return EmbeddingClient()

def get_llm_client() -> LLMClient:
    return LLMClient()

def get_rag_retrieval_service(
    vector_repo: VectorRepository = Depends(get_vector_repo),
    embedding_client: EmbeddingClient = Depends(get_embedding_client),
) -> RAGRetrievalService:
    return RAGRetrievalService(vector_repo=vector_repo, embedding_client=embedding_client)

def get_event_publisher() -> EventPublisher:
    return EventPublisher()

def require_role(allowed_roles: list[str]):
    """
    RBAC-зависимость для проверки роли пользователя (manager / admin).
    Передается в заголовке X-User-Role.
    """
    async def role_checker(x_user_role: str = Header("manager", alias="X-User-Role")) -> str:
        if x_user_role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Доступ запрещен. Требуется одна из ролей: {allowed_roles}",
            )
        return x_user_role
    return role_checker

