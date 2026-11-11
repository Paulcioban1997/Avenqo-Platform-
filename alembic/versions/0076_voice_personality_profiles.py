"""Add personality profiles, barge-in and realtime provider settings to voice_business_configs.

Revision ID: 0076_voice_personality_profiles
Revises: 0075_voice_display_name
"""

from alembic import op
import sqlalchemy as sa

revision = "0076_voice_personality_profiles"
down_revision = "0075_voice_display_name"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {item["name"]: item for item in sa.inspect(bind).get_columns("voice_business_configs")}
    with op.batch_alter_table("voice_business_configs") as batch:
        if "personality_preset" not in columns:
            batch.add_column(sa.Column("personality_preset", sa.String(64), nullable=False, server_default="professional_premium_warm"))
        if "professionalism_level" not in columns:
            batch.add_column(sa.Column("professionalism_level", sa.Integer(), nullable=False, server_default="100"))
        if "warmth_level" not in columns:
            batch.add_column(sa.Column("warmth_level", sa.Integer(), nullable=False, server_default="85"))
        if "humor_level" not in columns:
            batch.add_column(sa.Column("humor_level", sa.Integer(), nullable=False, server_default="40"))
        if "formality_level" not in columns:
            batch.add_column(sa.Column("formality_level", sa.Integer(), nullable=False, server_default="65"))
        if "response_length" not in columns:
            batch.add_column(sa.Column("response_length", sa.String(32), nullable=False, server_default="adaptive"))
        if "allow_natural_interruptions" not in columns:
            batch.add_column(sa.Column("allow_natural_interruptions", sa.Boolean(), nullable=False, server_default=sa.text("true")))
        if "preferred_accent" not in columns:
            batch.add_column(sa.Column("preferred_accent", sa.String(64), nullable=True))
        if "realtime_provider" not in columns:
            batch.add_column(sa.Column("realtime_provider", sa.String(32), nullable=False, server_default="retell"))
        if "gemini_live_enabled" not in columns:
            batch.add_column(sa.Column("gemini_live_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")))


def downgrade() -> None:
    with op.batch_alter_table("voice_business_configs") as batch:
        batch.drop_column("gemini_live_enabled")
        batch.drop_column("realtime_provider")
        batch.drop_column("preferred_accent")
        batch.drop_column("allow_natural_interruptions")
        batch.drop_column("response_length")
        batch.drop_column("formality_level")
        batch.drop_column("humor_level")
        batch.drop_column("warmth_level")
        batch.drop_column("professionalism_level")
        batch.drop_column("personality_preset")
