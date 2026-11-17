from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.enums import GmailConnectionStatus
from app.db.models.base import Base


class GmailConnection(Base):
    __tablename__ = "gmail_connections"

    gmail_account_id: Mapped[UUID] = mapped_column(
        ForeignKey("gmail_accounts.id", ondelete="CASCADE"), primary_key=True,
    )
    client_id: Mapped[str | None] = mapped_column(Text)
    client_secret_ciphertext: Mapped[str | None] = mapped_column(Text)
    refresh_token_ciphertext: Mapped[str | None] = mapped_column(Text)
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default="{}",
    )
    status: Mapped[GmailConnectionStatus] = mapped_column(
        SqlEnum(
            GmailConnectionStatus,
            name="gmail_connection_status",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda statuses: [status.value for status in statuses],
        ),
        server_default=GmailConnectionStatus.PENDING.value,
    )
    synced_through_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    next_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True,
    )
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[UUID | None] = mapped_column(Uuid)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    generation: Mapped[int] = mapped_column(server_default="0")

    pending_client_id: Mapped[str | None] = mapped_column(Text)
    pending_client_secret_ciphertext: Mapped[str | None] = mapped_column(Text)
    oauth_state_digest: Mapped[str | None] = mapped_column(
        String(64), unique=True,
    )
    oauth_browser_digest: Mapped[str | None] = mapped_column(String(64))
    oauth_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )
