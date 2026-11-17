"""Persist customer feedback linked to a published offer version."""
from alembic import op
import sqlalchemy as sa


revision = "0004_offer_responses"
down_revision = "0003_agent_settings"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "offer_response",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("offer_version_id", sa.Uuid(), nullable=False),
        sa.Column("author_user_id", sa.Uuid(), nullable=True),
        sa.Column("author_name", sa.String(length=200), nullable=False),
        sa.Column("author_email", sa.String(length=320), nullable=True),
        sa.Column("channel", sa.String(length=16), nullable=False, server_default="portal"),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["author_user_id"], ["user_account.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["user_account.id"]),
        sa.ForeignKeyConstraint(["offer_version_id"], ["offer_version.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_offer_response_offer_version_id", "offer_response", ["offer_version_id"])


def downgrade():
    op.drop_index("ix_offer_response_offer_version_id", table_name="offer_response")
    op.drop_table("offer_response")
