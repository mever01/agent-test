"""Schedule automatic indexing of imported threads."""

from alembic import op
import sqlalchemy as sa

revision = "002_rag_indexing"
down_revision = "001_gmail_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("threads", sa.Column("rag_updated_at", sa.DateTime(timezone=True)))
    op.add_column("threads", sa.Column("rag_indexed_at", sa.DateTime(timezone=True)))
    op.create_index("ix_threads_rag_updated_at", "threads", ["rag_updated_at"])
    op.execute("""
        UPDATE threads SET rag_updated_at = now()
        WHERE EXISTS (
            SELECT 1 FROM gmail_accounts
            WHERE gmail_accounts.id = threads.gmail_account_id
              AND gmail_accounts.gmail_email IS NOT NULL
        )
    """)


def downgrade() -> None:
    op.drop_index("ix_threads_rag_updated_at", table_name="threads")
    op.drop_column("threads", "rag_indexed_at")
    op.drop_column("threads", "rag_updated_at")
