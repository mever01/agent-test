from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
import logging

from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx

from app.agent.service import AgentService
from app.api.v1 import api_v1_router
from app.broker.rag.producer import RAGProducer
from app.broker.rag.topology import RAGTopology
from app.configs import settings
from app.configs.gmail import GMAIL_CALLBACK_PATH
from app.db.dao.gmail.gmail import GmailDAO
from app.db.dao.db_mail.draft import DraftDAO
from app.db.dao.db_mail.raw_email import RawEmailDAO
from app.db.dao.db_mail.thread import ThreadDAO
from app.db.dao.rag.document_chunk import DocumentChunkDAO
from app.db.dao.rag.email_chunk import EmailChunkDAO
from app.db.dao.user import UserRepository
from app.db.session import AsyncSessionLocal, engine, init_db
from app.external_api_clients.embedding_client import EmbeddingClient
from app.external_api_clients.gmail.client import GmailClient
from app.external_api_clients.llm_client import LLMClient
from app.services.auth_service import AuthService
from app.services.db_mail.draft import DraftService
from app.services.db_mail.raw_email import RawEmailService
from app.services.db_mail.thread import ThreadService
from app.services.gmail.gmail_service import GmailService
from app.services.rag.retrieval.document.service import DocumentRetrievalService
from app.services.rag.retrieval.email.service import EmailRetrievalService

from core.broker.client import RabbitMQClient

logger = logging.getLogger(__name__)


class GmailCallbackAccessFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Uvicorn includes the query string in the access-log target.
        args = record.args
        return not (
            isinstance(args, tuple) and len(args) == 5
            and str(args[2]).partition("?")[0].rstrip("/") == GMAIL_CALLBACK_PATH
        )


logging.getLogger("uvicorn.access").addFilter(GmailCallbackAccessFilter())


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with AsyncExitStack() as stack:
        stack.push_async_callback(engine.dispose)
        await init_db()
        gmail = settings.gmail
        if gmail.redirect_uri and gmail.frontend_url and gmail.encryption_key:
            cipher = Fernet(gmail.encryption_key.get_secret_value().encode())
            http = await stack.enter_async_context(httpx.AsyncClient(timeout=15))
            app.state.gmail_service = GmailService(
                GmailDAO(AsyncSessionLocal),
                GmailClient(http, str(gmail.redirect_uri)),
                cipher,
            )
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
        raw_email_dao = RawEmailDAO(AsyncSessionLocal)
        app.state.raw_email_service = RawEmailService(raw_email_dao)
        app.state.email_retrieval_service = EmailRetrievalService(
            raw_email_dao, EmailChunkDAO(AsyncSessionLocal),
            app.state.embedding_client,
        )
        app.state.thread_service = ThreadService(ThreadDAO(AsyncSessionLocal))
        app.state.draft_service = DraftService(DraftDAO(AsyncSessionLocal))
        document_search = DocumentRetrievalService(
            DocumentChunkDAO(AsyncSessionLocal), app.state.embedding_client,
            top_k=settings.agent.top_k_documents,
        )
        app.state.agent_service = AgentService(
            llm_client=app.state.llm_client,
            email_search=app.state.email_retrieval_service,
            thread_service=app.state.thread_service,
            draft_service=app.state.draft_service,
            document_search=document_search,
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
    allow_origins=[settings.gmail.frontend_origin or "*"],
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
