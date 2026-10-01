"""Extend AI provider attempts with Phase 4 normalized attribution and pricing snapshots.

Revision ID: 0029_ai_usage_attribution_and_pricing_snapshot
Revises: 0028_ai_tool_execution_idempotency
"""

from alembic import op
import sqlalchemy as sa


revision = "0029_ai_usage_attribution_and_pricing_snapshot"
down_revision = "0028_ai_tool_execution_idempotency"
branch_labels = None
depends_on = None


_COLUMNS = (
    sa.Column("user_id", sa.UUID(), nullable=True),
    sa.Column("conversation_id", sa.UUID(), nullable=True),
    sa.Column("agent_id", sa.String(length=100), nullable=True),
    sa.Column("module_id", sa.String(length=100), nullable=True),
    sa.Column("idempotency_key", sa.String(length=255), nullable=True),
    sa.Column("cached_output_tokens", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("audio_input_units", sa.Numeric(20, 8), nullable=False, server_default="0"),
    sa.Column("audio_output_units", sa.Numeric(20, 8), nullable=False, server_default="0"),
    sa.Column("request_status", sa.String(length=32), nullable=False, server_default="completed"),
    sa.Column("fallback_reason", sa.String(length=100), nullable=True),
    sa.Column("pricing_version", sa.String(length=100), nullable=True),
    sa.Column("pricing_source", sa.String(length=255), nullable=True),
    sa.Column("pricing_effective_from", sa.String(length=32), nullable=True),
    sa.Column("cached_output_cost_per_million_usd", sa.Numeric(20, 8), nullable=False, server_default="0"),
    sa.Column("reasoning_cost_per_million_usd", sa.Numeric(20, 8), nullable=False, server_default="0"),
    sa.Column("avenqo_credits_reserved", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("avenqo_credits_charged", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("avenqo_credits_released", sa.Integer(), nullable=False, server_default="0"),
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {column["name"] for column in inspector.get_columns("tenant_ai_provider_attempts")}
    with op.batch_alter_table("tenant_ai_provider_attempts") as batch_op:
        for column in _COLUMNS:
            if column.name not in existing:
                batch_op.add_column(column)

    inspector = sa.inspect(bind)
    indexes = {index["name"] for index in inspector.get_indexes("tenant_ai_provider_attempts")}
    for name, column in (
        ("ix_ai_provider_attempt_user_id", "user_id"),
        ("ix_ai_provider_attempt_conversation_id", "conversation_id"),
        ("ix_ai_provider_attempt_agent_id", "agent_id"),
        ("ix_ai_provider_attempt_module_id", "module_id"),
        ("ix_ai_provider_attempt_idempotency_key", "idempotency_key"),
    ):
        if name not in indexes:
            op.create_index(name, "tenant_ai_provider_attempts", [column], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = {index["name"] for index in inspector.get_indexes("tenant_ai_provider_attempts")}
    for name in (
        "ix_ai_provider_attempt_idempotency_key",
        "ix_ai_provider_attempt_module_id",
        "ix_ai_provider_attempt_agent_id",
        "ix_ai_provider_attempt_conversation_id",
        "ix_ai_provider_attempt_user_id",
    ):
        if name in indexes:
            op.drop_index(name, table_name="tenant_ai_provider_attempts")

    existing = {column["name"] for column in inspector.get_columns("tenant_ai_provider_attempts")}
    with op.batch_alter_table("tenant_ai_provider_attempts") as batch_op:
        for column in reversed(_COLUMNS):
            if column.name in existing:
                batch_op.drop_column(column.name)
