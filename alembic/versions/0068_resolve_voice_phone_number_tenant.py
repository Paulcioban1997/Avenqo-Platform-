"""Add secure resolver function for inbound phone number tenant resolution under RLS.

Revision ID: 0068_resolve_voice_phone_number_tenant
Revises: 0067_resolve_voice_call_tenant_owner
"""

from alembic import op
import sqlalchemy as sa

revision = "0068_resolve_voice_phone_number_tenant"
down_revision = "0067_resolve_voice_call_tenant_owner"
branch_labels = None
depends_on = None


def _is_postgres(bind) -> bool:
    dialect = getattr(bind, "dialect", None)
    return dialect is not None and getattr(dialect, "name", None) == "postgresql"


_RESOLVER_SQL = """
CREATE OR REPLACE FUNCTION public.resolve_voice_phone_number_tenant(
    p_phone_number text
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
STABLE
SET search_path = public, pg_temp
AS $$
DECLARE
    v_company_id uuid;
    v_norm text;
BEGIN
    IF p_phone_number IS NULL OR trim(p_phone_number) = '' THEN
        RETURN NULL;
    END IF;

    v_norm := regexp_replace(p_phone_number, '[^0-9+]', '', 'g');
    IF NOT starts_with(v_norm, '+') THEN
        IF starts_with(v_norm, '1') AND length(v_norm) = 11 THEN
            v_norm := '+' || v_norm;
        ELSIF length(v_norm) = 10 THEN
            v_norm := '+1' || v_norm;
        ELSE
            v_norm := '+' || v_norm;
        END IF;
    END IF;

    SELECT company_id INTO v_company_id
    FROM voice_phone_numbers
    WHERE (phone_number = p_phone_number OR phone_number = v_norm)
      AND status = 'ACTIVE'
      AND provider = 'telnyx'
    LIMIT 1;

    RETURN v_company_id;
END;
$$;
"""


def upgrade() -> None:
    bind = op.get_bind()
    if _is_postgres(bind):
        bind.execute(sa.text(_RESOLVER_SQL))
        try:
            owner = bind.execute(
                sa.text("SELECT r.rolname FROM pg_class c JOIN pg_roles r ON c.relowner = r.oid WHERE c.relname = 'voice_phone_numbers'")
            ).scalar() or "postgres"
            bind.execute(sa.text(f"ALTER FUNCTION public.resolve_voice_phone_number_tenant(text) OWNER TO {owner};"))
        except Exception:
            try:
                bind.execute(sa.text("ALTER FUNCTION public.resolve_voice_phone_number_tenant(text) OWNER TO postgres;"))
            except Exception:
                pass
        bind.execute(sa.text("GRANT EXECUTE ON FUNCTION public.resolve_voice_phone_number_tenant(text) TO PUBLIC;"))
        try:
            bind.execute(sa.text("GRANT EXECUTE ON FUNCTION public.resolve_voice_phone_number_tenant(text) TO avenqo_app;"))
        except Exception:
            pass


def downgrade() -> None:
    bind = op.get_bind()
    if _is_postgres(bind):
        bind.execute(sa.text("DROP FUNCTION IF EXISTS public.resolve_voice_phone_number_tenant(text);"))
