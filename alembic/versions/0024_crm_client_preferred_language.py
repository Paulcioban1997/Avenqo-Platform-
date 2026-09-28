"""Add tenant customer preferred language."""

from alembic import op
import sqlalchemy as sa

revision = "0024_crm_client_preferred_language"
down_revision = "0023_crm_appointment_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("crm_clients")}
    if "preferred_language" not in columns:
        op.add_column(
            "crm_clients",
            sa.Column("preferred_language", sa.String(length=16), nullable=False, server_default="fr"),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("crm_clients")}
    if "preferred_language" in columns:
        op.drop_column("crm_clients", "preferred_language")