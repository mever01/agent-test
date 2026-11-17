"""Index source messages instead of generated thread summaries."""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "003_email_chunks"
down_revision = "002_rag_indexing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("raw_emails", sa.Column(
        "rag_updated_at", sa.DateTime(timezone=True),
        server_default=sa.func.now(), nullable=False,
    ))
    op.add_column("raw_emails", sa.Column(
        "rag_indexed_at", sa.DateTime(timezone=True),
    ))
    op.create_index("ix_raw_emails_rag_updated_at", "raw_emails", ["rag_updated_at"])
    op.create_table(
        "email_chunks",
        sa.Column(
            "id", sa.Uuid(), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "email_id", sa.Uuid(),
            sa.ForeignKey("raw_emails.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=False),
        sa.UniqueConstraint("email_id", "chunk_index", name="uq_email_chunks_index"),
    )
    op.create_index("ix_email_chunks_email_id", "email_chunks", ["email_id"])
    op.drop_index("ix_threads_rag_updated_at", table_name="threads")
    op.drop_column("threads", "rag_indexed_at")
    op.drop_column("threads", "rag_updated_at")


def downgrade() -> None:
    op.add_column("threads", sa.Column("rag_updated_at", sa.DateTime(timezone=True)))
    op.add_column("threads", sa.Column("rag_indexed_at", sa.DateTime(timezone=True)))
    op.create_index("ix_threads_rag_updated_at", "threads", ["rag_updated_at"])
    op.drop_table("email_chunks")
    op.drop_index("ix_raw_emails_rag_updated_at", table_name="raw_emails")
    op.drop_column("raw_emails", "rag_indexed_at")
    op.drop_column("raw_emails", "rag_updated_at")
