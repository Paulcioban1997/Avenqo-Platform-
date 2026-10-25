"""Workspace OS, security MFA and document tables."""

from alembic import op
import sqlalchemy as sa

revision = "0049_workspace_security_and_business_os"
down_revision = "0048_billing_test_documents"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    return column in {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("users"):
        if not _has_column("users", "department"):
            op.add_column("users", sa.Column("department", sa.String(120), nullable=True))
        if not _has_column("users", "mfa_secret_encrypted"):
            op.add_column("users", sa.Column("mfa_secret_encrypted", sa.String(255), nullable=True))
        if not _has_column("users", "mfa_enabled"):
            op.add_column("users", sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))

    if inspector.has_table("auth_sessions"):
        if not _has_column("auth_sessions", "ip_address"):
            op.add_column("auth_sessions", sa.Column("ip_address", sa.String(64), nullable=True))
        if not _has_column("auth_sessions", "user_agent"):
            op.add_column("auth_sessions", sa.Column("user_agent", sa.String(512), nullable=True))
        if not _has_column("auth_sessions", "last_seen_at"):
            op.add_column("auth_sessions", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))

    if inspector.has_table("company_onboarding"):
        if not _has_column("company_onboarding", "current_step"):
            op.add_column("company_onboarding", sa.Column("current_step", sa.String(64), nullable=True))
        if not _has_column("company_onboarding", "draft_payload"):
            op.add_column("company_onboarding", sa.Column("draft_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))

    tables = {
        "login_events": lambda: op.create_table(
            "login_events",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("session_id", sa.Uuid(), nullable=True),
            sa.Column("outcome", sa.String(32), nullable=False, server_default="success"),
            sa.Column("ip_address", sa.String(64), nullable=True),
            sa.Column("user_agent", sa.String(512), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        ),
        "employee_invitations": lambda: op.create_table(
            "employee_invitations",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("invited_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("email", sa.String(255), nullable=False, index=True),
            sa.Column("role", sa.String(32), nullable=False, server_default="user"),
            sa.Column("job_title", sa.String(120), nullable=False, server_default="Employee"),
            sa.Column("department", sa.String(120), nullable=True),
            sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
            sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        ),
        "employee_responsibilities": lambda: op.create_table(
            "employee_responsibilities",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("title", sa.String(180), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("assigned_by_user_id", sa.Uuid(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        ),
        "employee_tasks": lambda: op.create_table(
            "employee_tasks",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("assignee_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("created_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("title", sa.String(220), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("priority", sa.String(16), nullable=False, server_default="medium"),
            sa.Column("status", sa.String(24), nullable=False, server_default="open"),
            sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        ),
        "tenant_documents": lambda: op.create_table(
            "tenant_documents",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("uploaded_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("kind", sa.String(24), nullable=False, index=True),
            sa.Column("filename", sa.String(255), nullable=False),
            sa.Column("content_type", sa.String(120), nullable=False, server_default="application/octet-stream"),
            sa.Column("byte_size", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("sha256", sa.String(64), nullable=False),
            sa.Column("extracted_text", sa.Text(), nullable=False, server_default=""),
            sa.Column("classification", sa.String(80), nullable=True),
            sa.Column("analysis_json", sa.Text(), nullable=True),
            sa.Column("analysis_disclaimer", sa.Text(), nullable=True),
            sa.Column("storage_path", sa.String(512), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        ),
        "media_generations": lambda: op.create_table(
            "media_generations",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("created_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("kind", sa.String(32), nullable=False, server_default="text"),
            sa.Column("prompt", sa.Text(), nullable=False),
            sa.Column("output_text", sa.Text(), nullable=False, server_default=""),
            sa.Column("status", sa.String(24), nullable=False, server_default="completed"),
            sa.Column("provider", sa.String(40), nullable=True),
            sa.Column("credits_used", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        ),
        "automation_workflows": lambda: op.create_table(
            "automation_workflows",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("created_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(180), nullable=False),
            sa.Column("trigger_type", sa.String(64), nullable=False),
            sa.Column("action_type", sa.String(64), nullable=False),
            sa.Column("condition_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("action_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_status", sa.String(32), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        ),
        "automation_runs": lambda: op.create_table(
            "automation_runs",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("workflow_id", sa.Uuid(), sa.ForeignKey("automation_workflows.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("idempotency_key", sa.String(120), nullable=False),
            sa.Column("status", sa.String(32), nullable=False, server_default="completed"),
            sa.Column("detail", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("company_id", "idempotency_key", name="uq_automation_run_idempotency"),
        ),
    }
    for name, create in tables.items():
        if not inspector.has_table(name):
            create()

    if bind.dialect.name == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION avenqo_tenant_id() RETURNS uuid AS $$
            BEGIN
              RETURN NULLIF(current_setting('app.current_company_id', true), '')::uuid;
            EXCEPTION WHEN others THEN
              RETURN NULL;
            END;
            $$ LANGUAGE plpgsql STABLE;
            """
        )
        for table in (
            "employee_tasks",
            "employee_responsibilities",
            "employee_invitations",
            "login_events",
            "tenant_documents",
            "media_generations",
            "automation_workflows",
            "automation_runs",
        ):
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            op.execute(
                f"""
                DROP POLICY IF EXISTS {table}_tenant_isolation ON {table};
                CREATE POLICY {table}_tenant_isolation ON {table}
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


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in (
            "automation_runs",
            "automation_workflows",
            "media_generations",
            "tenant_documents",
            "login_events",
            "employee_invitations",
            "employee_responsibilities",
            "employee_tasks",
        ):
            op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
    for table in (
        "automation_runs",
        "automation_workflows",
        "media_generations",
        "tenant_documents",
        "employee_tasks",
        "employee_responsibilities",
        "employee_invitations",
        "login_events",
    ):
        if sa.inspect(bind).has_table(table):
            op.drop_table(table)
