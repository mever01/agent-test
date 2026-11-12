"""Add an idempotency key for draft creation."""

import sqlalchemy as sa

from alembic import op

revision = "003_draft_operation"
down_revision = "003_password_hash_length"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not any(column["name"] == "operation_id" for column in inspector.get_columns("drafts")):
        op.add_column("drafts", sa.Column("operation_id", sa.Uuid(), nullable=True))
    constraints = inspector.get_unique_constraints("drafts")
    if not any(item["name"] == "uq_drafts_operation_id" for item in constraints):
        op.create_unique_constraint("uq_drafts_operation_id", "drafts", ["operation_id"])


def downgrade() -> None:
    op.drop_constraint("uq_drafts_operation_id", "drafts", type_="unique")
    op.drop_column("drafts", "operation_id")
