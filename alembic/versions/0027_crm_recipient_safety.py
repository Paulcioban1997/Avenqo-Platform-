"""Persist CRM recipient safety and notification idempotency."""

from alembic import op
import sqlalchemy as sa


revision = "0027_crm_recipient_safety"
down_revision = "0026_crm_calendar_event_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    op.add_column(
        "crm_clients",
        sa.Column("is_synthetic", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "crm_clients",
        sa.Column("communications_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_crm_clients_is_synthetic", "crm_clients", ["is_synthetic"])
    name_condition = (
        "lower(first_name || ' ' || last_name) ~ '(^|[^a-z])(test|demo|seed|fake|fixture|sample|dummy)([^a-z]|$)'"
        if bind.dialect.name == "postgresql"
        else "lower(first_name || ' ' || last_name) LIKE '%test%' OR lower(first_name || ' ' || last_name) LIKE '%demo%' OR lower(first_name || ' ' || last_name) LIKE '%seed%' OR lower(first_name || ' ' || last_name) LIKE '%fake%' OR lower(first_name || ' ' || last_name) LIKE '%fixture%' OR lower(first_name || ' ' || last_name) LIKE '%sample%' OR lower(first_name || ' ' || last_name) LIKE '%dummy%'"
    )
    op.execute(sa.text(f"""
        UPDATE crm_clients
        SET is_synthetic = true, communications_enabled = false
        WHERE lower(email) = 'crm_test_client@avenqo.ca'
           OR lower(email) LIKE '%@example.com'
           OR lower(email) LIKE '%@example.net'
           OR lower(email) LIKE '%@example.org'
           OR lower(email) LIKE '%@avenqo-audit.ca'
           OR lower(email) LIKE '%@avenqo-e2e.ca'
           OR lower(email) LIKE '%@production-test.ca'
           OR {name_condition}
    """))
    with op.batch_alter_table("crm_communications") as batch_op:
        batch_op.create_unique_constraint(
            "uq_crm_communication_delivery",
            ["company_id", "appointment_id", "channel", "subject"],
        )


def downgrade() -> None:
    with op.batch_alter_table("crm_communications") as batch_op:
        batch_op.drop_constraint("uq_crm_communication_delivery", type_="unique")
    op.drop_index("ix_crm_clients_is_synthetic", table_name="crm_clients")
    op.drop_column("crm_clients", "communications_enabled")
    op.drop_column("crm_clients", "is_synthetic")