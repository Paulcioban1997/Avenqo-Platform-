"""Allow tenant Voice setup before a phone number is provisioned.

Revision ID: 0045_voice_optional_phone_number
Revises: 0044_voice_number_references
Create Date: 2026-10-06 22:05:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0045_voice_optional_phone_number"
down_revision = "0044_voice_number_references"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {item["name"]: item for item in sa.inspect(op.get_bind()).get_columns("voice_business_configs")}
    with op.batch_alter_table("voice_business_configs") as batch:
        if "telnyx_phone_number" in columns and not columns["telnyx_phone_number"]["nullable"]:
            batch.alter_column("telnyx_phone_number", existing_type=sa.String(32), nullable=True)


def downgrade() -> None:
    missing = op.get_bind().execute(sa.text(
        "SELECT count(*) FROM voice_business_configs WHERE telnyx_phone_number IS NULL"
    )).scalar()
    if missing:
        raise RuntimeError("Cannot restore mandatory phone number while unconfigured tenant Voice setups exist")
    with op.batch_alter_table("voice_business_configs") as batch:
        batch.alter_column("telnyx_phone_number", existing_type=sa.String(32), nullable=False)
