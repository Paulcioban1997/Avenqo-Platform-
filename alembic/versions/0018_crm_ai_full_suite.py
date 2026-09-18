"""Add full multi-tenant CRM AI suite tables.

Revision ID: 0018_crm_ai_full_suite
Revises: 0017_canonical_data_layers
"""

from alembic import op
import sqlalchemy as sa


revision = "0018_crm_ai_full_suite"
down_revision = "0017_canonical_data_layers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("crm_clients"):
        op.create_table(
            "crm_clients",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("company_id", sa.Uuid(), nullable=False),
            sa.Column("first_name", sa.String(length=100), nullable=False),
            sa.Column("last_name", sa.String(length=100), nullable=False),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("phone", sa.String(length=50), nullable=True),
            sa.Column("company_name", sa.String(length=255), nullable=True),
            sa.Column("industry_type", sa.String(length=50), server_default="general", nullable=False),
            sa.Column("industry_metadata", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(length=50), server_default="active", nullable=False),
            sa.Column("tags", sa.JSON(), nullable=False),
            sa.Column("total_revenue", sa.Float(), server_default="0", nullable=False),
            sa.Column("attendance_rate", sa.Float(), server_default="100", nullable=False),
            sa.Column("appointments_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_crm_clients_company_id", "crm_clients", ["company_id"])
        op.create_index("ix_crm_clients_email", "crm_clients", ["email"])
        op.create_index("ix_crm_clients_phone", "crm_clients", ["phone"])
        op.create_index("ix_crm_clients_status", "crm_clients", ["status"])
        op.create_index("ix_crm_clients_is_deleted", "crm_clients", ["is_deleted"])

    if not inspector.has_table("crm_addresses"):
        op.create_table(
            "crm_addresses",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("company_id", sa.Uuid(), nullable=False),
            sa.Column("client_id", sa.Uuid(), nullable=False),
            sa.Column("address_type", sa.String(length=50), server_default="primary", nullable=False),
            sa.Column("street", sa.String(length=255), nullable=False),
            sa.Column("city", sa.String(length=100), nullable=False),
            sa.Column("state_province", sa.String(length=100), nullable=True),
            sa.Column("postal_code", sa.String(length=20), nullable=False),
            sa.Column("country", sa.String(length=100), server_default="Canada", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["client_id"], ["crm_clients.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_crm_addresses_company_id", "crm_addresses", ["company_id"])
        op.create_index("ix_crm_addresses_client_id", "crm_addresses", ["client_id"])

    if not inspector.has_table("crm_services"):
        op.create_table(
            "crm_services",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("company_id", sa.Uuid(), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("duration_minutes", sa.Integer(), server_default="60", nullable=False),
            sa.Column("price", sa.Float(), server_default="0", nullable=False),
            sa.Column("currency", sa.String(length=10), server_default="CAD", nullable=False),
            sa.Column("category", sa.String(length=100), nullable=True),
            sa.Column("color_hex", sa.String(length=20), server_default="#0076FF", nullable=True),
            sa.Column("buffer_before_minutes", sa.Integer(), server_default="0", nullable=False),
            sa.Column("buffer_after_minutes", sa.Integer(), server_default="0", nullable=False),
            sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_crm_services_company_id", "crm_services", ["company_id"])
        op.create_index("ix_crm_services_name", "crm_services", ["name"])
        op.create_index("ix_crm_services_is_active", "crm_services", ["is_active"])

    if not inspector.has_table("crm_employees"):
        op.create_table(
            "crm_employees",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("company_id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=True),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("email", sa.String(length=255), nullable=True),
            sa.Column("phone", sa.String(length=50), nullable=True),
            sa.Column("role_title", sa.String(length=100), nullable=True),
            sa.Column("color_hex", sa.String(length=20), server_default="#00D4FF", nullable=True),
            sa.Column("working_hours", sa.JSON(), nullable=False),
            sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_crm_employees_company_id", "crm_employees", ["company_id"])
        op.create_index("ix_crm_employees_user_id", "crm_employees", ["user_id"])
        op.create_index("ix_crm_employees_is_active", "crm_employees", ["is_active"])

    if not inspector.has_table("crm_appointments"):
        op.create_table(
            "crm_appointments",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("company_id", sa.Uuid(), nullable=False),
            sa.Column("client_id", sa.Uuid(), nullable=False),
            sa.Column("service_id", sa.Uuid(), nullable=True),
            sa.Column("employee_id", sa.Uuid(), nullable=True),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
            sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
            sa.Column("duration_minutes", sa.Integer(), server_default="60", nullable=False),
            sa.Column("status", sa.String(length=50), server_default="confirmed", nullable=False),
            sa.Column("price", sa.Float(), server_default="0", nullable=False),
            sa.Column("currency", sa.String(length=10), server_default="CAD", nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("industry_data", sa.JSON(), nullable=False),
            sa.Column("calendar_provider", sa.String(length=50), nullable=True),
            sa.Column("external_event_id", sa.String(length=255), nullable=True),
            sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["client_id"], ["crm_clients.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["service_id"], ["crm_services.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["employee_id"], ["crm_employees.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_crm_appointments_company_id", "crm_appointments", ["company_id"])
        op.create_index("ix_crm_appointments_client_id", "crm_appointments", ["client_id"])
        op.create_index("ix_crm_appointments_service_id", "crm_appointments", ["service_id"])
        op.create_index("ix_crm_appointments_employee_id", "crm_appointments", ["employee_id"])
        op.create_index("ix_crm_appointments_start_time", "crm_appointments", ["start_time"])
        op.create_index("ix_crm_appointments_end_time", "crm_appointments", ["end_time"])
        op.create_index("ix_crm_appointments_status", "crm_appointments", ["status"])
        op.create_index("ix_crm_appointments_external_event_id", "crm_appointments", ["external_event_id"])
        op.create_index("ix_crm_appointments_is_deleted", "crm_appointments", ["is_deleted"])

    if not inspector.has_table("crm_notes"):
        op.create_table(
            "crm_notes",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("company_id", sa.Uuid(), nullable=False),
            sa.Column("client_id", sa.Uuid(), nullable=True),
            sa.Column("appointment_id", sa.Uuid(), nullable=True),
            sa.Column("author_id", sa.Uuid(), nullable=True),
            sa.Column("author_name", sa.String(length=150), server_default="Système", nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("pinned", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["client_id"], ["crm_clients.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["appointment_id"], ["crm_appointments.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_crm_notes_company_id", "crm_notes", ["company_id"])
        op.create_index("ix_crm_notes_client_id", "crm_notes", ["client_id"])
        op.create_index("ix_crm_notes_appointment_id", "crm_notes", ["appointment_id"])

    if not inspector.has_table("crm_pipelines"):
        op.create_table(
            "crm_pipelines",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("company_id", sa.Uuid(), nullable=False),
            sa.Column("name", sa.String(length=150), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("is_default", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_crm_pipelines_company_id", "crm_pipelines", ["company_id"])

    if not inspector.has_table("crm_pipeline_stages"):
        op.create_table(
            "crm_pipeline_stages",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("pipeline_id", sa.Uuid(), nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("position", sa.Integer(), server_default="0", nullable=False),
            sa.Column("color_hex", sa.String(length=20), server_default="#0076FF", nullable=False),
            sa.Column("win_probability", sa.Float(), server_default="0.2", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["pipeline_id"], ["crm_pipelines.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_crm_pipeline_stages_pipeline_id", "crm_pipeline_stages", ["pipeline_id"])

    if not inspector.has_table("crm_communications"):
        op.create_table(
            "crm_communications",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("company_id", sa.Uuid(), nullable=False),
            sa.Column("client_id", sa.Uuid(), nullable=False),
            sa.Column("appointment_id", sa.Uuid(), nullable=True),
            sa.Column("channel", sa.String(length=50), server_default="email", nullable=False),
            sa.Column("direction", sa.String(length=20), server_default="outbound", nullable=False),
            sa.Column("subject", sa.String(length=255), nullable=True),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=50), server_default="sent", nullable=False),
            sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["client_id"], ["crm_clients.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["appointment_id"], ["crm_appointments.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_crm_communications_company_id", "crm_communications", ["company_id"])
        op.create_index("ix_crm_communications_client_id", "crm_communications", ["client_id"])
        op.create_index("ix_crm_communications_appointment_id", "crm_communications", ["appointment_id"])

    if not inspector.has_table("crm_reminders"):
        op.create_table(
            "crm_reminders",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("company_id", sa.Uuid(), nullable=False),
            sa.Column("appointment_id", sa.Uuid(), nullable=False),
            sa.Column("remind_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("channel", sa.String(length=50), server_default="email", nullable=False),
            sa.Column("is_sent", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["appointment_id"], ["crm_appointments.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_crm_reminders_company_id", "crm_reminders", ["company_id"])
        op.create_index("ix_crm_reminders_appointment_id", "crm_reminders", ["appointment_id"])
        op.create_index("ix_crm_reminders_remind_at", "crm_reminders", ["remind_at"])
        op.create_index("ix_crm_reminders_is_sent", "crm_reminders", ["is_sent"])

    if not inspector.has_table("crm_automations"):
        op.create_table(
            "crm_automations",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("company_id", sa.Uuid(), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("trigger_type", sa.String(length=100), nullable=False),
            sa.Column("trigger_config", sa.JSON(), nullable=False),
            sa.Column("action_type", sa.String(length=100), nullable=False),
            sa.Column("action_config", sa.JSON(), nullable=False),
            sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("execution_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_crm_automations_company_id", "crm_automations", ["company_id"])
        op.create_index("ix_crm_automations_is_active", "crm_automations", ["is_active"])

    if not inspector.has_table("crm_calendar_connections"):
        op.create_table(
            "crm_calendar_connections",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("company_id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=True),
            sa.Column("provider", sa.String(length=50), server_default="google", nullable=False),
            sa.Column("account_email", sa.String(length=255), nullable=False),
            sa.Column("calendar_id", sa.String(length=255), server_default="primary", nullable=False),
            sa.Column("encrypted_credentials", sa.Text(), nullable=False),
            sa.Column("sync_status", sa.String(length=50), server_default="connected", nullable=False),
            sa.Column("sync_error", sa.Text(), nullable=True),
            sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_crm_calendar_connections_company_id", "crm_calendar_connections", ["company_id"])

    if not inspector.has_table("crm_activity_log"):
        op.create_table(
            "crm_activity_log",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("company_id", sa.Uuid(), nullable=False),
            sa.Column("entity_type", sa.String(length=50), nullable=False),
            sa.Column("entity_id", sa.Uuid(), nullable=False),
            sa.Column("action", sa.String(length=100), nullable=False),
            sa.Column("actor_id", sa.Uuid(), nullable=True),
            sa.Column("actor_name", sa.String(length=150), server_default="Système / IA", nullable=False),
            sa.Column("details", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_crm_activity_log_company_id", "crm_activity_log", ["company_id"])
        op.create_index("ix_crm_activity_log_entity_id", "crm_activity_log", ["entity_id"])


def downgrade() -> None:
    op.drop_table("crm_activity_log")
    op.drop_table("crm_calendar_connections")
    op.drop_table("crm_automations")
    op.drop_table("crm_reminders")
    op.drop_table("crm_communications")
    op.drop_table("crm_pipeline_stages")
    op.drop_table("crm_pipelines")
    op.drop_table("crm_notes")
    op.drop_table("crm_appointments")
    op.drop_table("crm_employees")
    op.drop_table("crm_services")
    op.drop_table("crm_addresses")
    op.drop_table("crm_clients")
