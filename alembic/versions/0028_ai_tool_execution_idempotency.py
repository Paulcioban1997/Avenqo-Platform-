"""Persist idempotent execution receipts for mutating AI tools."""

from alembic import op
import sqlalchemy as sa


revision = "0028_ai_tool_execution_idempotency"
down_revision = "0027_crm_recipient_safety"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_tool_execution_records",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=True),
        sa.Column("request_id", sa.String(length=100), nullable=False),
        sa.Column("agent_id", sa.String(length=100), nullable=False),
        sa.Column("tool_name", sa.String(length=128), nullable=False),
        sa.Column("arguments_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="in_progress"),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "request_id", "tool_name",
            name="uq_ai_tool_execution_request_tool",
        ),
    )
    op.create_index(
        "ix_ai_tool_execution_records_company_id",
        "ai_tool_execution_records", ["company_id"], unique=False,
    )
    op.create_index(
        "ix_ai_tool_execution_records_user_id",
        "ai_tool_execution_records", ["user_id"], unique=False,
    )
    op.create_index(
        "ix_ai_tool_execution_records_conversation_id",
        "ai_tool_execution_records", ["conversation_id"], unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ai_tool_execution_records_conversation_id", table_name="ai_tool_execution_records")
    op.drop_index("ix_ai_tool_execution_records_user_id", table_name="ai_tool_execution_records")
    op.drop_index("ix_ai_tool_execution_records_company_id", table_name="ai_tool_execution_records")
    op.drop_table("ai_tool_execution_records")