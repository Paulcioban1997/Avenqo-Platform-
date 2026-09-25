"""Add company_memberships table, missing commerce_connections columns, and normalize plans.

Revision ID: 0020_memberships_and_connector_columns
Revises: 0019_enterprise_quotes
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0020_memberships_and_connector_columns"
down_revision = "0019_enterprise_quotes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names(schema="public"))

    # 1. Create company_memberships table if missing
    if "company_memberships" not in tables:
        # Check if user_role enum exists
        user_role_enum = postgresql.ENUM("OWNER", "ADMIN", "USER", "PLATFORM_ADMIN", name="user_role", create_type=False)
        op.create_table(
            "company_memberships",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
            sa.Column("role", user_role_enum, nullable=False, server_default="USER"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.UniqueConstraint("user_id", "company_id", name="uq_user_company_membership"),
        )
        op.create_index("ix_company_memberships_user_id", "company_memberships", ["user_id"])
        op.create_index("ix_company_memberships_company_id", "company_memberships", ["company_id"])

        # Seed memberships for all existing users
        bind.execute(sa.text("""
            INSERT INTO company_memberships (user_id, company_id, role, is_active, created_at, updated_at)
            SELECT id, company_id, role, is_active, created_at, updated_at
            FROM users
            WHERE company_id IS NOT NULL
            ON CONFLICT (user_id, company_id) DO NOTHING
        """))

    # 2. Add missing columns to commerce_connections if missing
    if "commerce_connections" in tables:
        existing_cols = {c["name"] for c in inspector.get_columns("commerce_connections", schema="public")}

        missing_cols = [
            ("records_created", sa.Column("records_created", sa.Integer(), nullable=False, server_default="0")),
            ("records_updated", sa.Column("records_updated", sa.Integer(), nullable=False, server_default="0")),
            ("records_failed", sa.Column("records_failed", sa.Integer(), nullable=False, server_default="0")),
            ("sync_run_id", sa.Column("sync_run_id", sa.String(length=64), nullable=True)),
            ("sync_error_code", sa.Column("sync_error_code", sa.String(length=64), nullable=True)),
            ("sync_error_message", sa.Column("sync_error_message", sa.Text(), nullable=True)),
            ("last_heartbeat", sa.Column("last_heartbeat", sa.DateTime(timezone=True), nullable=True)),
            ("sync_completed_at", sa.Column("sync_completed_at", sa.DateTime(timezone=True), nullable=True)),
            ("sync_failed_at", sa.Column("sync_failed_at", sa.DateTime(timezone=True), nullable=True)),
        ]

        for col_name, col_def in missing_cols:
            if col_name not in existing_cols:
                op.add_column("commerce_connections", col_def)

    # 3. Normalize legacy plan codes in companies and billing_accounts
    bind.execute(sa.text("""
        UPDATE companies
        SET subscription_plan = 'base'
        WHERE LOWER(subscription_plan) = 'demo'
    """))

    bind.execute(sa.text("""
        UPDATE billing_accounts
        SET plan_code = 'base'
        WHERE LOWER(plan_code) = 'demo'
    """))

    # Ensure all companies have a billing_account
    bind.execute(sa.text("""
        INSERT INTO billing_accounts (id, company_id, plan_code, status, cancel_at_period_end, current_period_end, created_at, updated_at)
        SELECT gen_random_uuid(), c.id, COALESCE(c.subscription_plan, 'base'), 'trialing', false, CURRENT_TIMESTAMP + INTERVAL '14 days', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM companies c
        LEFT JOIN billing_accounts b ON b.company_id = c.id
        WHERE b.id IS NULL
    """))


def downgrade() -> None:
    pass
