"""Persist the Voice microphone frame cursor across reconnects.

Revision ID: 0034_voice_audio_frame_sequence
Revises: 0033_voice_provider_usage_pricing
"""

from alembic import op
import sqlalchemy as sa

revision = "0034_voice_audio_frame_sequence"
down_revision = "0033_voice_provider_usage_pricing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("voice_central_sessions")}
    if "last_audio_sequence" not in columns:
        with op.batch_alter_table("voice_central_sessions") as batch_op:
            batch_op.add_column(
                sa.Column("last_audio_sequence", sa.Integer(), nullable=False, server_default="-1")
            )


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("voice_central_sessions")}
    if "last_audio_sequence" in columns:
        with op.batch_alter_table("voice_central_sessions") as batch_op:
            batch_op.drop_column("last_audio_sequence")
