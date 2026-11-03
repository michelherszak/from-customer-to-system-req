"""offer commercial fields

Revision ID: 0002_offer_commercial_fields
Revises: 39b2fbb17b37
Create Date: 2026-09-24
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_offer_commercial_fields"
down_revision = "39b2fbb17b37"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("offer_version", sa.Column("recipient", sa.String(length=300), nullable=True))
    op.add_column("offer_version", sa.Column("customer_reference", sa.String(length=200), nullable=True))
    op.add_column("offer_version", sa.Column("internal_reference", sa.String(length=200), nullable=True))
    op.add_column("offer_version", sa.Column("payment_plan", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))

def downgrade():
    op.drop_column("offer_version", "payment_plan")
    op.drop_column("offer_version", "internal_reference")
    op.drop_column("offer_version", "customer_reference")
    op.drop_column("offer_version", "recipient")
