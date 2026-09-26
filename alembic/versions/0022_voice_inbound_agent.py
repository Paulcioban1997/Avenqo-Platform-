"""Add tenant-scoped inbound voice agent configuration and call logs."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0022_voice_inbound_agent"
down_revision = "0021_retail_source_states"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "voice_business_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_name", sa.String(255), nullable=False),
        sa.Column("timezone_name", sa.String(80), nullable=False),
        sa.Column("opening_hours", sa.JSON(), nullable=False),
        sa.Column("services", sa.JSON(), nullable=False),
        sa.Column("transfer_phone", sa.String(40), nullable=True),
        sa.Column("telnyx_phone_number", sa.String(32), nullable=False),
        sa.Column("preferred_language", sa.String(8), nullable=False),
        sa.Column("greeting_message", sa.Text(), nullable=False),
        sa.Column("retell_agent_id", sa.String(128), nullable=False),
        sa.Column("retell_sip_uri", sa.String(512), nullable=False),
        sa.Column("voice_api_key_hash", sa.String(64), nullable=False),
        sa.Column("voice_api_key_last4", sa.String(4), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", name="uq_voice_business_config_company"),
        sa.UniqueConstraint("telnyx_phone_number", name="uq_voice_business_telnyx_number"),
        sa.UniqueConstraint("retell_agent_id", name="uq_voice_business_retell_agent"),
        sa.UniqueConstraint("voice_api_key_hash", name="uq_voice_business_api_key_hash"),
    )
    op.create_index("ix_voice_business_configs_company_id", "voice_business_configs", ["company_id"])

    op.create_table(
        "voice_calls",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("config_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("telnyx_call_control_id", sa.String(255), nullable=True),
        sa.Column("retell_call_id", sa.String(255), nullable=True),
        sa.Column("caller_phone", sa.String(40), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="incoming"),
        sa.Column("uncertainty_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("sms_status", sa.String(32), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["config_id"], ["voice_business_configs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["appointment_id"], ["crm_appointments.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telnyx_call_control_id", name="uq_voice_calls_telnyx_id"),
        sa.UniqueConstraint("retell_call_id", name="uq_voice_calls_retell_id"),
    )
    op.create_index("ix_voice_calls_company_id", "voice_calls", ["company_id"])
    op.create_index("ix_voice_calls_config_id", "voice_calls", ["config_id"])
    op.create_index("ix_voice_calls_appointment_id", "voice_calls", ["appointment_id"])
    op.create_index("ix_voice_calls_status", "voice_calls", ["status"])

    op.create_table(
        "voice_tool_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("config_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_id", sa.String(255), nullable=False),
        sa.Column("tool_name", sa.String(64), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["config_id"], ["voice_business_configs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("config_id", "action_id", name="uq_voice_tool_action_id"),
    )
    op.create_index("ix_voice_tool_actions_company_id", "voice_tool_actions", ["company_id"])
    op.create_index("ix_voice_tool_actions_config_id", "voice_tool_actions", ["config_id"])


def downgrade() -> None:
    op.drop_index("ix_voice_tool_actions_config_id", table_name="voice_tool_actions")
    op.drop_index("ix_voice_tool_actions_company_id", table_name="voice_tool_actions")
    op.drop_table("voice_tool_actions")
    op.drop_index("ix_voice_calls_status", table_name="voice_calls")
    op.drop_index("ix_voice_calls_appointment_id", table_name="voice_calls")
    op.drop_index("ix_voice_calls_config_id", table_name="voice_calls")
    op.drop_index("ix_voice_calls_company_id", table_name="voice_calls")
    op.drop_table("voice_calls")
    op.drop_index("ix_voice_business_configs_company_id", table_name="voice_business_configs")
    op.drop_table("voice_business_configs")