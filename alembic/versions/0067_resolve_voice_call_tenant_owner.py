"""Ensure resolve_voice_call_tenant function is owned by table owner to bypass FORCE RLS.

Revision ID: 0067_resolve_voice_call_tenant_owner
Revises: 0066_resolve_voice_call_tenant
"""

from alembic import op
import sqlalchemy as sa

revision = "0067_resolve_voice_call_tenant_owner"
down_revision = "0066_resolve_voice_call_tenant"
branch_labels = None
depends_on = None


def _is_postgres(bind) -> bool:
    dialect = getattr(bind, "dialect", None)
    return dialect is not None and getattr(dialect, "name", None) == "postgresql"


def upgrade() -> None:
    bind = op.get_bind()
    if _is_postgres(bind):
        # Determine table owner of voice_calls (typically postgres superuser in Railway)
        try:
            owner = bind.execute(
                sa.text("SELECT r.rolname FROM pg_class c JOIN pg_roles r ON c.relowner = r.oid WHERE c.relname = 'voice_calls'")
            ).scalar() or "postgres"
            bind.execute(sa.text(f"ALTER FUNCTION public.resolve_voice_call_tenant(uuid, text) OWNER TO {owner};"))
        except Exception:
            try:
                bind.execute(sa.text("ALTER FUNCTION public.resolve_voice_call_tenant(uuid, text) OWNER TO postgres;"))
            except Exception:
                pass
        bind.execute(sa.text("GRANT EXECUTE ON FUNCTION public.resolve_voice_call_tenant(uuid, text) TO PUBLIC;"))
        try:
            bind.execute(sa.text("GRANT EXECUTE ON FUNCTION public.resolve_voice_call_tenant(uuid, text) TO avenqo_app;"))
        except Exception:
            pass


def downgrade() -> None:
    pass
