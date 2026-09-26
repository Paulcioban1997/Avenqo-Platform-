"""Add tenant-scoped appointment idempotency keys."""

from alembic import op
import sqlalchemy as sa


revision = "0023_crm_appointment_idempotency"
down_revision = "0022_voice_inbound_agent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("crm_appointments", sa.Column("idempotency_key", sa.String(length=255), nullable=True))
    op.create_unique_constraint(
        "uq_crm_appointments_company_idempotency",
        "crm_appointments",
        ["company_id", "idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_crm_appointments_company_idempotency", "crm_appointments", type_="unique")
    op.drop_column("crm_appointments", "idempotency_key")