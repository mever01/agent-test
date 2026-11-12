"""Initial schema with users, threads, raw_emails, drafts, document_chunks, email_thread_vectors

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-11-11 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import pgvector
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Включаем расширения PostgreSQL
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")

    # 2. Создаем ENUM типы PostgreSQL
    user_role_enum = postgresql.ENUM('manager', 'admin', name='user_role', create_type=False)
    user_role_enum.create(op.get_bind(), checkfirst=True)

    thread_status_enum = postgresql.ENUM('active', 'closed', name='thread_status', create_type=False)
    thread_status_enum.create(op.get_bind(), checkfirst=True)

    # 3. Таблица пользователей (RBAC)
    op.create_table(
        'users',
        sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('role', user_role_enum, nullable=False, server_default='manager'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)

    # 4. Таблица цепочек (Threads)
    op.create_table(
        'threads',
        sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('subject', sa.Text(), nullable=False),
        sa.Column('client_email', sa.String(length=255), nullable=False),
        sa.Column('status', thread_status_enum, nullable=False, server_default='active'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_threads_client_email', 'threads', ['client_email'], unique=False)

    # 5. Таблица сырых писем (Raw Emails)
    op.create_table(
        'raw_emails',
        sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('thread_id', sa.Uuid(), nullable=False),
        sa.Column('sender', sa.String(length=255), nullable=False),
        sa.Column('recipient', sa.String(length=255), nullable=False),
        sa.Column('date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('subject', sa.Text(), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column(
            'tsv',
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('russian', coalesce(subject, '') || ' ' || coalesce(body, ''))", persisted=True),
            nullable=True
        ),
        sa.ForeignKeyConstraint(['thread_id'], ['threads.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_raw_emails_thread_id', 'raw_emails', ['thread_id'], unique=False)
    op.create_index('ix_raw_emails_sender', 'raw_emails', ['sender'], unique=False)
    op.create_index('ix_raw_emails_recipient', 'raw_emails', ['recipient'], unique=False)
    op.create_index('ix_raw_emails_date', 'raw_emails', ['date'], unique=False)
    op.execute("CREATE INDEX IF NOT EXISTS idx_raw_emails_tsv ON raw_emails USING GIN(tsv);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_raw_emails_body_trgm ON raw_emails USING GIN(body gin_trgm_ops);")

    # 5. Таблица черновиков (Drafts)
    op.create_table(
        'drafts',
        sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('thread_id', sa.Uuid(), nullable=False),
        sa.Column('recipient', sa.String(length=255), nullable=False),
        sa.Column('subject', sa.Text(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['thread_id'], ['threads.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_drafts_thread_id', 'drafts', ['thread_id'], unique=False)

    # 6. Таблица векторных чанков регламентов (Document Chunks)
    op.create_table(
        'document_chunks',
        sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('doc_id', sa.String(length=64), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column(
            'tsv',
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('russian', content)", persisted=True),
            nullable=True
        ),
        sa.Column('embedding', Vector(1024), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_document_chunks_doc_id', 'document_chunks', ['doc_id'], unique=False)
    op.execute("CREATE INDEX IF NOT EXISTS idx_doc_chunks_tsv ON document_chunks USING GIN(tsv);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_doc_chunks_vector ON document_chunks USING hnsw (embedding vector_cosine_ops);")

    # 7. Таблица векторных саммари тредов (Email Thread Vectors)
    op.create_table(
        'email_thread_vectors',
        sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('thread_id', sa.Uuid(), nullable=False),
        sa.Column('date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('embedding', Vector(1024), nullable=True),
        sa.ForeignKeyConstraint(['thread_id'], ['threads.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('thread_id')
    )
    op.create_index('ix_email_thread_vectors_date', 'email_thread_vectors', ['date'], unique=False)
    op.execute("CREATE INDEX IF NOT EXISTS idx_email_vecs_vector ON email_thread_vectors USING hnsw (embedding vector_cosine_ops);")


def downgrade() -> None:
    op.drop_table('email_thread_vectors')
    op.drop_table('document_chunks')
    op.drop_table('drafts')
    op.drop_table('raw_emails')
    op.drop_table('threads')
    op.drop_table('users')
    op.execute("DROP TYPE IF EXISTS thread_status;")
    op.execute("DROP TYPE IF EXISTS user_role;")

