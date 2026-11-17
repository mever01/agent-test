from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class GmailAccount(Base):
    __tablename__ = "gmail_accounts"
    __table_args__ = (
        UniqueConstraint("owner_id", "gmail_email", name="uq_gmail_accounts_email"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid4, server_default=func.gen_random_uuid(),
    )
    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"), index=True,
    )
    name: Mapped[str] = mapped_column(String(255))
    gmail_email: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )
