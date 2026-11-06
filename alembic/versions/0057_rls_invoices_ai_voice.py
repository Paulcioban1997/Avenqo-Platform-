"""FORCE RLS on billing invoices, AI conversations and voice calls.

Additive PostgreSQL-only policies. SQLite tests are unchanged. No data rewrite.
"""

from alembic import op
import sqlalchemy as sa

revision = "0057_rls_invoices_ai_voice"
down_revision = "0056_rls_crm_commerce_datasets"
branch_labels = depends_on = None

_TABLES = (
    "billing_invoices",
    "ai_conversations",
    "ai_messages",
    "voice_calls",
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
