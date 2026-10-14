"""FORCE RLS on CRM, commerce, dataset and audit tables already listed as tenant-scoped.

Additive PostgreSQL-only policies. SQLite tests are unchanged. No data rewrite.
"""

from alembic import op
import sqlalchemy as sa

revision = "0056_rls_crm_commerce_datasets"
down_revision = "0055_voice_call_policy"
branch_labels = depends_on = None

_TABLES = (
    "datasets",
    "commerce_connections",
    "crm_clients",
    "crm_appointments",
    "crm_notes",
    "audit_log_entries",
)


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    inspector = sa.inspect(bind)
    for table in _TABLES:
        if not inspector.has_table(table):
            continue
        columns = {column["name"] for column in inspector.get_columns(table)}
        if "company_id" not in columns:
            continue
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        op.execute(
            f"""
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
    raise RuntimeError("Preserve tenant RLS; use an approved forward repair instead of dropping policies")
