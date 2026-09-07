"""Add immutable tenant AI provider attempt ledger.

Revision ID: 0011_ai_provider_attempt_ledger
Revises: 0010_dataset_relationship_cardinality
"""

from alembic import op
import sqlalchemy as sa


revision = "0011_ai_provider_attempt_ledger"
down_revision = "0010_dataset_relationship_cardinality"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "tenant_ai_provider_attempts" in inspector.get_table_names():
        return
    op.create_table(
        "tenant_ai_provider_attempts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("avenqo_request_id", sa.String(length=100), nullable=False),
        sa.Column("provider_request_id", sa.String(length=255), nullable=True),
        sa.Column("operation", sa.String(length=50), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("failure_category", sa.String(length=50), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cached_input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reasoning_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tool_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("provider_cost_usd", sa.Numeric(20, 12), nullable=False),
        sa.Column("input_cost_per_million_usd", sa.Numeric(20, 8), nullable=False),
        sa.Column("cached_input_cost_per_million_usd", sa.Numeric(20, 8), nullable=False),
        sa.Column("output_cost_per_million_usd", sa.Numeric(20, 8), nullable=False),
        sa.Column("tool_call_cost_usd", sa.Numeric(20, 12), nullable=False),
        sa.Column("avenqo_credits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("attempt_number > 0", name="ck_ai_provider_attempt_number_positive"),
        sa.CheckConstraint("provider_cost_usd >= 0", name="ck_ai_provider_attempt_cost_nonnegative"),
        sa.CheckConstraint("avenqo_credits >= 0", name="ck_ai_provider_attempt_credits_nonnegative"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "avenqo_request_id",
            "attempt_number",
            name="uq_ai_provider_attempt_company_request_number",
        ),
    )
    op.create_index(
        op.f("ix_tenant_ai_provider_attempts_company_id"),
        "tenant_ai_provider_attempts",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tenant_ai_provider_attempts_avenqo_request_id"),
        "tenant_ai_provider_attempts",
        ["avenqo_request_id"],
        unique=False,
    )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "tenant_ai_provider_attempts" not in inspector.get_table_names():
        return
    op.drop_index(op.f("ix_tenant_ai_provider_attempts_avenqo_request_id"), table_name="tenant_ai_provider_attempts")
    op.drop_index(op.f("ix_tenant_ai_provider_attempts_company_id"), table_name="tenant_ai_provider_attempts")
    op.drop_table("tenant_ai_provider_attempts")