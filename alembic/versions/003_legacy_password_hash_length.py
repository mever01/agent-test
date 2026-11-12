"""Recognize databases migrated by the previous authentication implementation.

Both upgrade paths already have users.email and a text password_hash at
this point. The previous implementation also added drafts.operation_id.
"""

revision = "003_password_hash_length"
down_revision = "002_user_credentials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
