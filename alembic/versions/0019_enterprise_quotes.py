"""Add enterprise_quotes table.

Revision ID: 0019_enterprise_quotes
Revises: 0018_crm_ai_full_suite
"""

from alembic import op
import sqlalchemy as sa


revision = "0019_enterprise_quotes"
down_revision = "0018_crm_ai_full_suite"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("enterprise_quotes"):
        op.create_table(
            "enterprise_quotes",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("reference_id", sa.String(length=32), nullable=False),
            sa.Column("company_id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("contact_name", sa.String(length=255), nullable=False),
            sa.Column("contact_email", sa.String(length=255), nullable=False),
            sa.Column("contact_phone", sa.String(length=64), nullable=True),
            sa.Column("requested_modules", sa.JSON(), nullable=False),
            sa.Column("estimated_users", sa.Integer(), nullable=True),
            sa.Column("monthly_volume", sa.String(length=128), nullable=True),
            sa.Column("required_integrations", sa.JSON(), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=32), server_default="received", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_enterprise_quotes_company_id", "enterprise_quotes", ["company_id"])
        op.create_index("ix_enterprise_quotes_reference_id", "enterprise_quotes", ["reference_id"], unique=True)
        op.create_index("ix_enterprise_quotes_status", "enterprise_quotes", ["status"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("enterprise_quotes"):
        op.drop_table("enterprise_quotes")
