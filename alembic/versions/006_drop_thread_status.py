"""Remove the status of mail threads."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM

revision = "006_drop_thread_status"
down_revision = "005_provider_neutral_mail"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("threads", "status")
    op.execute("DROP TYPE thread_status")


def downgrade() -> None:
    thread_status = ENUM("active", "closed", name="thread_status", create_type=False)
    thread_status.create(op.get_bind())
    op.add_column(
        "threads",
        sa.Column("status", thread_status, nullable=False, server_default="active"),
    )
