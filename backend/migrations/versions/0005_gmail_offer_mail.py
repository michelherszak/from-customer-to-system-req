"""Store Gmail OAuth connections and offer email threads."""
from alembic import op
import sqlalchemy as sa


revision = "0005_gmail_offer_mail"
down_revision = "0004_offer_responses"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("offer_response", sa.Column("provider_message_id", sa.String(length=255), nullable=True))
    op.create_index("ix_offer_response_provider_message_id", "offer_response", ["provider_message_id"], unique=True)
    op.create_table(
        "gmail_connection",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("encrypted_refresh_token", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["user_account.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user_account.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "user_id"),
    )
    op.create_index("ix_gmail_connection_tenant_id", "gmail_connection", ["tenant_id"])
    op.create_index("ix_gmail_connection_user_id", "gmail_connection", ["user_id"])
    op.create_table(
        "gmail_offer_thread",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("offer_version_id", sa.Uuid(), nullable=False),
        sa.Column("gmail_connection_id", sa.Uuid(), nullable=False),
        sa.Column("gmail_thread_id", sa.String(length=255), nullable=False),
        sa.Column("recipient_email", sa.String(length=320), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["user_account.id"]),
        sa.ForeignKeyConstraint(["gmail_connection_id"], ["gmail_connection.id"]),
        sa.ForeignKeyConstraint(["offer_version_id"], ["offer_version.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("offer_version_id", "gmail_thread_id"),
    )
    op.create_index("ix_gmail_offer_thread_offer_version_id", "gmail_offer_thread", ["offer_version_id"])
    op.create_index("ix_gmail_offer_thread_gmail_connection_id", "gmail_offer_thread", ["gmail_connection_id"])


def downgrade():
    op.drop_index("ix_gmail_offer_thread_gmail_connection_id", table_name="gmail_offer_thread")
    op.drop_index("ix_gmail_offer_thread_offer_version_id", table_name="gmail_offer_thread")
    op.drop_table("gmail_offer_thread")
    op.drop_index("ix_gmail_connection_user_id", table_name="gmail_connection")
    op.drop_index("ix_gmail_connection_tenant_id", table_name="gmail_connection")
    op.drop_table("gmail_connection")
    op.drop_index("ix_offer_response_provider_message_id", table_name="offer_response")
    op.drop_column("offer_response", "provider_message_id")
