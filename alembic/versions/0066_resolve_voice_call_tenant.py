"""Add secure resolver function for inbound Voice call tenant resolution under RLS.

Revision ID: 0066_resolve_voice_call_tenant
Revises: 0065_company_routing_nips
"""

from alembic import op
import sqlalchemy as sa

revision = "0066_resolve_voice_call_tenant"
down_revision = "0065_company_routing_nips"
branch_labels = None
depends_on = None


def _is_postgres(bind) -> bool:
    dialect = getattr(bind, "dialect", None)
    return dialect is not None and getattr(dialect, "name", None) == "postgresql"


_RESOLVER_SQL = """
CREATE OR REPLACE FUNCTION public.resolve_voice_call_tenant(
    p_call_id uuid DEFAULT NULL,
    p_call_control_id text DEFAULT NULL
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
STABLE
SET search_path = public, pg_temp
AS $$
DECLARE
    v_company_id uuid;
BEGIN
    IF p_call_id IS NOT NULL THEN
        SELECT company_id INTO v_company_id
        FROM voice_calls
        WHERE id = p_call_id
        LIMIT 1;
        IF v_company_id IS NOT NULL THEN
            RETURN v_company_id;
        END IF;
    END IF;

    IF p_call_control_id IS NOT NULL AND p_call_control_id != '' THEN
        SELECT company_id INTO v_company_id
        FROM voice_calls
        WHERE telnyx_call_control_id = p_call_control_id
        LIMIT 1;
        IF v_company_id IS NOT NULL THEN
            RETURN v_company_id;
        END IF;
    END IF;

    RETURN NULL;
END;
$$;
"""


def upgrade() -> None:
    bind = op.get_bind()
    if _is_postgres(bind):
        op.execute(_RESOLVER_SQL)
        op.execute("GRANT EXECUTE ON FUNCTION public.resolve_voice_call_tenant(uuid, text) TO PUBLIC;")


def downgrade() -> None:
    bind = op.get_bind()
    if _is_postgres(bind):
        op.execute("DROP FUNCTION IF EXISTS public.resolve_voice_call_tenant(uuid, text);")
