"""Add voice customization, personality, and tone settings to voice_business_configs.

Revision ID: 0046_voice_personalization_customization
Revises: 0045_voice_optional_phone_number
Create Date: 2026-10-08 20:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0046_voice_personalization_customization"
down_revision = "0045_voice_optional_phone_number"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {item["name"]: item for item in sa.inspect(op.get_bind()).get_columns("voice_business_configs")}
    with op.batch_alter_table("voice_business_configs") as batch:
        if "voice_id" not in columns:
            batch.add_column(sa.Column("voice_id", sa.String(64), nullable=False, server_default="alloy"))
        if "voice_provider" not in columns:
            batch.add_column(sa.Column("voice_provider", sa.String(32), nullable=False, server_default="openai"))
        if "speech_speed" not in columns:
            batch.add_column(sa.Column("speech_speed", sa.Float(), nullable=False, server_default="1.0"))
        if "personality_tone" not in columns:
            batch.add_column(sa.Column("personality_tone", sa.String(32), nullable=False, server_default="professionnel"))
        if "custom_pronunciation" not in columns:
            batch.add_column(sa.Column("custom_pronunciation", sa.String(255), nullable=True))
        if "farewell_message" not in columns:
            batch.add_column(sa.Column("farewell_message", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("voice_business_configs") as batch:
        batch.drop_column("farewell_message")
        batch.drop_column("custom_pronunciation")
        batch.drop_column("personality_tone")
        batch.drop_column("speech_speed")
        batch.drop_column("voice_provider")
        batch.drop_column("voice_id")
