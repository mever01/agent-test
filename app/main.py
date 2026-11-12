import logging
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agent.service import AgentService
from app.api.dependencies import get_mail_repo, get_rag_document_repo, get_rag_thread_repo
from app.api.v1 import api_v1_router
from app.broker.rag.producer import RAGProducer
from app.broker.rag.topology import RAGTopology
from app.configs import settings
from app.db.repositories.user_repository import UserRepository
from app.db.session import AsyncSessionLocal, engine, init_db
from core.broker.client import RabbitMQClient
from app.external_api_clients.embedding_client import EmbeddingClient
from app.external_api_clients.llm_client import LLMClient

from app.rag.retrieval.service import RAGRetrievalService
from app.services.auth_service import AuthService
from app.services.mail_service import MailService

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with AsyncExitStack() as stack:
        stack.push_async_callback(engine.dispose)
        await init_db()
        app.state.auth_service = AuthService(
            UserRepository(AsyncSessionLocal), settings.auth_session_ttl,
        )
        rabbitmq_client = await stack.enter_async_context(
            RabbitMQClient(url=settings.rabbitmq.url)
        )
        app.state.rabbitmq_client = rabbitmq_client
        channel = await rabbitmq_client.get_channel()
        resources = await RAGTopology(channel).setup()
        app.state.rag_producer = RAGProducer(rabbitmq_client, resources.exchanges.events.name)
        app.state.embedding_client = EmbeddingClient()
        stack.push_async_callback(app.state.embedding_client.close)
        app.state.llm_client = LLMClient()
        stack.push_async_callback(app.state.llm_client.close)
        app.state.agent_service = AgentService(
            llm_client=app.state.llm_client,
            mail_service=MailService(get_mail_repo(), app.state.rag_producer),
            rag_service=RAGRetrievalService(
                get_rag_document_repo(), get_rag_thread_repo(), app.state.embedding_client,
                top_k_documents=settings.agent.top_k_documents,
                top_k_threads=settings.agent.top_k_threads,
            ),
        )
        yield


app = FastAPI(
    title=settings.app.title,
    version=settings.app.version,
    debug=settings.app.debug,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_v1_router, prefix="/api")


@app.get("/health", tags=["Health"])
async def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "service": settings.app.title,
        "version": settings.app.version,
    }
