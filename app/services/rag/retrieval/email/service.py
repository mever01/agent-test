import logging
from uuid import UUID

import httpx

from app.db.dao.db_mail.raw_email import RawEmailDAO
from app.db.dao.rag.email_chunk import EmailChunkDAO
from app.dto.db_mail import MailSearchCriteria, MailSnippet
from app.external_api_clients.embedding_client import EmbeddingClient
from app.services.rag.retrieval.email.prompts import QUERY_EMBEDDING_INSTRUCTION
from app.services.rag.retrieval.email.ranking import merge_matches

logger = logging.getLogger(__name__)


class EmailRetrievalService:
    def __init__(
        self, emails: RawEmailDAO, chunks: EmailChunkDAO, embedding: EmbeddingClient,
    ) -> None:
        self._emails = emails
        self._chunks = chunks
        self._embedding = embedding

    async def search(
        self, criteria: MailSearchCriteria, *, owner_id: UUID | None, limit: int = 10,
    ) -> list[MailSnippet]:
        """Объединяет текстовый и векторный поиск с одинаковыми фильтрами доступа."""
        if limit <= 0:
            return []
        lexical = await self._emails.search_emails(
            criteria, owner_id=owner_id, limit=limit,
        )
        if not criteria.words:
            return lexical
        try:
            vector = await self._embedding.get_embedding(
                criteria.words, instruction=QUERY_EMBEDDING_INSTRUCTION,
            )
            semantic = await self._chunks.search(criteria, vector, owner_id, limit)
        except (httpx.HTTPError, ValueError):
            logger.warning("Semantic mail search unavailable")
            return lexical
        return merge_matches(lexical, semantic, limit)
