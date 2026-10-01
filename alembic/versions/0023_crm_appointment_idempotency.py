"""Add tenant-scoped appointment idempotency keys."""

from alembic import op
import sqlalchemy as sa


revision = "0023_crm_appointment_idempotency"
down_revision = "0022_voice_inbound_agent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("crm_appointments") as batch_op:
        batch_op.add_column(sa.Column("idempotency_key", sa.String(length=255), nullable=True))
        batch_op.create_unique_constraint(
            "uq_crm_appointments_company_idempotency",
            ["company_id", "idempotency_key"],
        )


def downgrade() -> None:
    with op.batch_alter_table("crm_appointments") as batch_op:
        batch_op.drop_constraint("uq_crm_appointments_company_idempotency", type_="unique")
        batch_op.drop_column("idempotency_key")