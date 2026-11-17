from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class EmailChunk(Base):
    __tablename__ = "email_chunks"
    __table_args__ = (
        UniqueConstraint("email_id", "chunk_index", name="uq_email_chunks_index"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid4, server_default=func.gen_random_uuid(),
    )
    email_id: Mapped[UUID] = mapped_column(
        ForeignKey("raw_emails.id", ondelete="CASCADE"), index=True,
    )
    chunk_index: Mapped[int]
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(1024))
