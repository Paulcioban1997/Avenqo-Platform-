"""Add voice_display_name to voice_business_configs.

Revision ID: 0075_voice_display_name
Revises: 0074_secure_download_nonces
"""

from alembic import op
import sqlalchemy as sa

revision = "0075_voice_display_name"
down_revision = "0074_secure_download_nonces"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {item["name"]: item for item in sa.inspect(bind).get_columns("voice_business_configs")}
    with op.batch_alter_table("voice_business_configs") as batch:
        if "voice_display_name" not in columns:
            batch.add_column(sa.Column("voice_display_name", sa.String(255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("voice_business_configs") as batch:
        batch.drop_column("voice_display_name")

