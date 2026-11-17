import uuid
from datetime import datetime
from typing import Any
from sqlalchemy import Computed, DateTime, ForeignKeyConstraint, String, Text
from sqlalchemy import UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import ENUM as pgEnum

from app.db.enums import AccountSource
from app.db.models.base import Base


class RawEmail(Base):
    __tablename__ = "raw_emails"
    __table_args__ = (
        ForeignKeyConstraint(
            ["thread_id", "account_source", "account_id"],
            ["threads.id", "threads.account_source", "threads.account_id"],
            name="fk_raw_emails_thread_account",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "account_source", "account_id", "message_id",
            name="uq_raw_emails_external_message",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    thread_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
        index=True,
    )
    account_source: Mapped[AccountSource] = mapped_column(
        pgEnum(
            AccountSource,
            name="account_source",
            values_callable=lambda values: [item.value for item in values],
        )
    )
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    message_id: Mapped[str] = mapped_column(Text)
    rag_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True,
    )
    rag_indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sender: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    recipient: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    tsv: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('russian', coalesce(subject, '') || ' ' || coalesce(body, ''))",
            persisted=True
        ),
        nullable=True,
    )

    thread = relationship("Thread", back_populates="emails")
