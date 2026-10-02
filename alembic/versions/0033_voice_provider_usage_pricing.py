"""Add modality-specific usage and pricing snapshots to provider attempts.

Revision ID: 0033_voice_provider_usage_pricing
Revises: 0032_voice_central_sessions
"""

from alembic import op
import sqlalchemy as sa

revision = "0033_voice_provider_usage_pricing"
down_revision = "0032_voice_central_sessions"
branch_labels = None
depends_on = None


_COLUMNS = (
    sa.Column("text_input_tokens", sa.Integer(), nullable=True),
    sa.Column("cached_text_input_tokens", sa.Integer(), nullable=True),
    sa.Column("text_output_tokens", sa.Integer(), nullable=True),
    sa.Column("cached_audio_input_units", sa.Numeric(20, 8), nullable=False, server_default="0"),
    sa.Column("audio_input_seconds", sa.Numeric(20, 8), nullable=False, server_default="0"),
    sa.Column("audio_input_cost_per_million_usd", sa.Numeric(20, 8), nullable=False, server_default="0"),
    sa.Column("cached_audio_input_cost_per_million_usd", sa.Numeric(20, 8), nullable=False, server_default="0"),
    sa.Column("audio_output_cost_per_million_usd", sa.Numeric(20, 8), nullable=False, server_default="0"),
    sa.Column("audio_input_cost_per_second_usd", sa.Numeric(20, 12), nullable=False, server_default="0"),
)


def upgrade() -> None:
    bind = op.get_bind()
    existing = {
        column["name"]
        for column in sa.inspect(bind).get_columns("tenant_ai_provider_attempts")
    }
    with op.batch_alter_table("tenant_ai_provider_attempts") as batch_op:
        for column in _COLUMNS:
            if column.name not in existing:
                batch_op.add_column(column)


def downgrade() -> None:
    bind = op.get_bind()
    existing = {
        column["name"]
        for column in sa.inspect(bind).get_columns("tenant_ai_provider_attempts")
    }
    with op.batch_alter_table("tenant_ai_provider_attempts") as batch_op:
        for column in reversed(_COLUMNS):
            if column.name in existing:
                batch_op.drop_column(column.name)
