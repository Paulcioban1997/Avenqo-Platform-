"""Add tenant call rules without changing existing call data or enabling audio."""
from alembic import op
import sqlalchemy as sa

revision = "0055_voice_call_policy"
down_revision = "0054_voice_provisioning"
branch_labels = depends_on = None


def upgrade():
    if "call_policy" not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("voice_business_configs")}:
        op.add_column("voice_business_configs", sa.Column("call_policy", sa.JSON(), nullable=True))


def downgrade():
    raise RuntimeError("Preserve tenant policies; use an approved forward repair")
