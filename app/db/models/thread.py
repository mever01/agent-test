import uuid
from datetime import datetime
from sqlalchemy import String, Text, DateTime, func, Uuid
from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects.postgresql import ENUM as pgEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.models.base import Base
from app.db.enums import AccountSource
from app.db.models.raw_email import RawEmail
from app.db.models.draft import Draft


class Thread(Base):
    __tablename__ = "threads"
    __table_args__ = (
        UniqueConstraint(
            "account_source", "account_id", "external_thread_id",
            name="uq_threads_external_thread",
        ),
        UniqueConstraint(
            "id", "account_source", "account_id", name="uq_threads_id_account",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    account_source: Mapped[AccountSource] = mapped_column(
        pgEnum(
            AccountSource,
            name="account_source",
            values_callable=lambda values: [item.value for item in values],
        )
    )
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    external_thread_id: Mapped[str] = mapped_column(Text)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    client_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    emails: Mapped[list[RawEmail]] = relationship(
        RawEmail,
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="RawEmail.date.asc()",
    )
    drafts: Mapped[list[Draft]] = relationship(
        Draft,
        back_populates="thread",
        cascade="all, delete-orphan",
    )
