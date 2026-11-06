"""FORCE RLS on remaining company_id business tables.

Additive and reversible. SQLite tests are a no-op. Does not rotate DATABASE_URL
and must not be applied to Production. Sandbox copy only until an explicit GO.
"""

from alembic import op

from backend.app.services.tenant_rls import RLS_EXPANSION_0060, apply_force_rls_policies, revoke_force_rls_policies

revision = "0060_rls_remaining_tenant_tables"
down_revision = "0059_migrate_role_schema_create"
branch_labels = depends_on = None


def upgrade():
    bind = op.get_bind()
    apply_force_rls_policies(bind, RLS_EXPANSION_0060)


def downgrade():
    bind = op.get_bind()
    revoke_force_rls_policies(bind, RLS_EXPANSION_0060)
