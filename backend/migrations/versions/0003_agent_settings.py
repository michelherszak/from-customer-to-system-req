"""Company-scoped agent settings; existing companies keep default behavior."""
from alembic import op
import sqlalchemy as sa
revision = "0003_agent_settings"
down_revision = "0002_offer_commercial_fields"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("tenant", sa.Column("agent_settings", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))

def downgrade():
    op.drop_column("tenant", "agent_settings")
