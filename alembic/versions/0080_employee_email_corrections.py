"""Store an owner request to correct one employee's email address.

Revision ID: 0080_employee_email_corrections
Revises: 0079_employee_permission_grants

The address changes only after the new inbox confirms it. The account,
job and permissions stay on the same row. Additive on SQLite and PostgreSQL.
"""

from alembic import op
import sqlalchemy as sa

revision = "0080_employee_email_corrections"
down_revision = "0079_employee_permission_grants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("employee_email_corrections"):
        return
    op.create_table(
        "employee_email_corrections",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("old_email", sa.String(255), nullable=False),
        sa.Column("new_email", sa.String(255), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=True),
        sa.Column("code_salt", sa.String(32), nullable=True),
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("token_hash", name="uq_employee_email_corrections_token_hash"),
    )
    op.create_index("ix_employee_email_corrections_company_id", "employee_email_corrections", ["company_id"])
    op.create_index("ix_employee_email_corrections_user_id", "employee_email_corrections", ["user_id"])
    op.create_index("ix_employee_email_corrections_new_email", "employee_email_corrections", ["new_email"])
    if bind.dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE employee_email_corrections ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE employee_email_corrections FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY employee_email_corrections_tenant_isolation
        ON employee_email_corrections
        USING (
          current_setting('app.bypass_rls', true) = 'on'
          OR company_id = avenqo_tenant_id()
        )
        WITH CHECK (
          current_setting('app.bypass_rls', true) = 'on'
          OR company_id = avenqo_tenant_id()
        )
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("employee_email_corrections"):
        return
    if bind.dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS employee_email_corrections_tenant_isolation ON employee_email_corrections")
    op.drop_table("employee_email_corrections")
