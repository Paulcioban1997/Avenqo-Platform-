"""Harden all tenant RLS policies: eliminate app.bypass_rls backdoor and secure dataset child tables.

Reversible. Does not rewrite rows or modify application DATABASE_URL.
"""

from alembic import op

from backend.app.services.tenant_rls import harden_all_tenant_rls_policies, revert_harden_all_tenant_rls_policies

revision = "0061b_harden_tenant_rls_no_bypass"
down_revision = "0061_tenant_hotpath_indexes"
branch_labels = depends_on = None


def upgrade():
    bind = op.get_bind()
    harden_all_tenant_rls_policies(bind)


def downgrade():
    bind = op.get_bind()
    revert_harden_all_tenant_rls_policies(bind)
