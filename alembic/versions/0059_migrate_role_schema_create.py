"""Allow the distinct migrator role to create schema objects.

Additive. Does not enable LOGIN and does not rewrite DATABASE_URL.
Alembic on live Sandbox still runs as the current migration identity until
a separate cutover GO.
"""

from alembic import op

from backend.app.services.postgres_app_role import ensure_application_roles

revision = "0059_migrate_role_schema_create"
down_revision = "0058_sandbox_app_db_roles"
branch_labels = depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    ensure_application_roles(bind)


def downgrade():
    raise RuntimeError("Keep migrator schema CREATE; do not revoke it from a deployed environment")
