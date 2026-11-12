"""Align the users email column with ORM and add password hashes."""

import sqlalchemy as sa

from alembic import op

revision = "002_user_credentials"
down_revision = "001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("users", "row_email", new_column_name="email")
    op.add_column("users", sa.Column("password_hash", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "password_hash")
    op.alter_column("users", "email", new_column_name="row_email")
