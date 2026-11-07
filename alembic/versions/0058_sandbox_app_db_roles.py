"""Create constrained PostgreSQL application and migrator roles.

Additive and idempotent. Roles stay NOLOGIN until an authorized operator
enables LOGIN with a password kept outside Git. This migration does not
change DATABASE_URL or table ownership.
"""

from alembic import op

from backend.app.services.postgres_app_role import ensure_application_roles

revision = "0058_sandbox_app_db_roles"
down_revision = "0057_rls_invoices_ai_voice"
branch_labels = depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    ensure_application_roles(bind)


def downgrade():
    raise RuntimeError("Preserve constrained database roles; do not drop them from a deployed environment")
