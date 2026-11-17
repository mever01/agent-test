"""Use provider-neutral identifiers and account-scoped mail constraints."""

from alembic import op
import sqlalchemy as sa

revision = "005_provider_neutral_mail"
down_revision = "004_mail_account_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("fk_raw_emails_thread_account", "raw_emails", type_="foreignkey")
    for constraint in sa.inspect(op.get_bind()).get_foreign_keys("threads"):
        if constraint["referred_table"] == "gmail_accounts":
            op.drop_constraint(constraint["name"], "threads", type_="foreignkey")
    op.drop_constraint("uq_threads_gmail_thread", "threads", type_="unique")
    op.drop_constraint("uq_threads_id_account", "threads", type_="unique")
    op.drop_constraint("uq_raw_emails_gmail_message", "raw_emails", type_="unique")

    op.alter_column("threads", "gmail_account_id", new_column_name="account_id")
    op.alter_column("threads", "gmail_thread_id", new_column_name="external_thread_id")
    op.alter_column("raw_emails", "gmail_account_id", new_column_name="account_id")
    op.alter_column("raw_emails", "gmail_message_id", new_column_name="message_id")

    op.create_unique_constraint(
        "uq_threads_external_thread", "threads",
        ["account_source", "account_id", "external_thread_id"],
    )
    op.create_unique_constraint(
        "uq_threads_id_account", "threads", ["id", "account_source", "account_id"],
    )
    op.create_unique_constraint(
        "uq_raw_emails_external_message", "raw_emails",
        ["account_source", "account_id", "message_id"],
    )
    op.create_foreign_key(
        "fk_raw_emails_thread_account", "raw_emails", "threads",
        ["thread_id", "account_source", "account_id"],
        ["id", "account_source", "account_id"], ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_raw_emails_thread_account", "raw_emails", type_="foreignkey")
    op.drop_constraint("uq_raw_emails_external_message", "raw_emails", type_="unique")
    op.drop_constraint("uq_threads_external_thread", "threads", type_="unique")
    op.drop_constraint("uq_threads_id_account", "threads", type_="unique")

    op.alter_column("threads", "account_id", new_column_name="gmail_account_id")
    op.alter_column("threads", "external_thread_id", new_column_name="gmail_thread_id")
    op.alter_column("raw_emails", "account_id", new_column_name="gmail_account_id")
    op.alter_column("raw_emails", "message_id", new_column_name="gmail_message_id")

    op.create_foreign_key(
        "threads_gmail_account_id_fkey", "threads", "gmail_accounts",
        ["gmail_account_id"], ["id"],
    )
    op.create_unique_constraint(
        "uq_threads_gmail_thread", "threads", ["gmail_account_id", "gmail_thread_id"],
    )
    op.create_unique_constraint(
        "uq_threads_id_account", "threads", ["id", "gmail_account_id"],
    )
    op.create_unique_constraint(
        "uq_raw_emails_gmail_message", "raw_emails",
        ["gmail_account_id", "gmail_message_id"],
    )
    op.create_foreign_key(
        "fk_raw_emails_thread_account", "raw_emails", "threads",
        ["thread_id", "gmail_account_id"], ["id", "gmail_account_id"],
        ondelete="CASCADE",
    )
