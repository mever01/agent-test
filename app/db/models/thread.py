import uuid
from datetime import datetime
from sqlalchemy import String, Text, DateTime, func, Uuid
from sqlalchemy.dialects.postgresql import ENUM as pgEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.models.base import Base
from app.db.enums import ThreadStatus
from app.db.models.raw_email import RawEmail
from app.db.models.draft import Draft
from app.db.models.email_thread_vector import EmailThreadVector


class Thread(Base):
    __tablename__ = "threads"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    client_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[ThreadStatus] = mapped_column(
        pgEnum(
            ThreadStatus,
            name="thread_status",
            values_callable=lambda x: [e.value for e in x]
        ),
        default=ThreadStatus.ACTIVE,
        server_default=ThreadStatus.ACTIVE.value,
        nullable=False,
    )
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
    vector_summary: Mapped[EmailThreadVector] = relationship(
        EmailThreadVector,
        back_populates="thread",
        uselist=False,
        cascade="all, delete-orphan",
    )





