"""Add tenant-scoped external calendar event identity."""

from alembic import op


revision = "0026_crm_calendar_event_identity"
down_revision = "0025_crm_custom_field_definitions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("crm_appointments") as batch_op:
        batch_op.create_unique_constraint(
            "uq_crm_appointments_company_calendar_event",
            ["company_id", "calendar_provider", "external_event_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("crm_appointments") as batch_op:
        batch_op.drop_constraint(
            "uq_crm_appointments_company_calendar_event",
            type_="unique",
        )