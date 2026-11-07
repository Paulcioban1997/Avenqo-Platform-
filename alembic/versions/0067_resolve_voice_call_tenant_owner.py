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
        owner = bind.execute(sa.text(
            "SELECT r.rolname FROM pg_class c "
            "JOIN pg_namespace n ON n.oid=c.relnamespace "
            "JOIN pg_roles r ON c.relowner=r.oid "
            "WHERE n.nspname='public' AND c.relname='voice_calls'"
        )).scalar_one()
        quoted_owner = bind.dialect.identifier_preparer.quote(owner)
        # Ownership is required by the resolver's security contract. A failed
        # ALTER FUNCTION must abort the migration, not leave the transaction
        # poisoned and silently fall back to a superuser-owned function.
        bind.execute(sa.text(
            f"ALTER FUNCTION public.resolve_voice_call_tenant(uuid, text) OWNER TO {quoted_owner}"
        ))
        bind.execute(sa.text("GRANT EXECUTE ON FUNCTION public.resolve_voice_call_tenant(uuid, text) TO PUBLIC;"))
        bind.execute(sa.text("GRANT EXECUTE ON FUNCTION public.resolve_voice_call_tenant(uuid, text) TO avenqo_app;"))


def downgrade() -> None:
    pass
