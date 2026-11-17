"""Persist the source of mail threads and messages."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM

revision = "004_mail_account_source"
down_revision = "003_email_chunks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    source = ENUM("gmail", name="account_source", create_type=False)
    source.create(op.get_bind(), checkfirst=True)
    op.add_column("threads", sa.Column(
        "account_source", source, server_default="gmail", nullable=False,
    ))
    op.add_column("raw_emails", sa.Column(
        "account_source", source, server_default="gmail", nullable=False,
    ))
    op.alter_column("threads", "account_source", server_default=None)
    op.alter_column("raw_emails", "account_source", server_default=None)


def downgrade() -> None:
    op.drop_column("raw_emails", "account_source")
    op.drop_column("threads", "account_source")
    ENUM(name="account_source").drop(op.get_bind(), checkfirst=True)
