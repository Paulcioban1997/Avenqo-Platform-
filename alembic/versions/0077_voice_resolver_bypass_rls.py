"""Let inbound voice resolvers read their own lookup tables under FORCE RLS.

Revision ID: 0077_voice_resolver_bypass_rls
Revises: 0076_voice_personality_profiles

avenqo_owner does not have BYPASSRLS. FORCE ROW LEVEL SECURITY therefore hides
every row from SECURITY DEFINER functions owned by that role when no tenant
GUC is set. Inbound calls then miss a dedicated number and fall into the
shared dispatcher. The lookup role bypasses RLS only inside these two
functions. avenqo_app stays constrained.
"""

from alembic import op
import sqlalchemy as sa

revision = "0077_voice_resolver_bypass_rls"
down_revision = "0076_voice_personality_profiles"
branch_labels = None
depends_on = None

RESOLVER_ROLE = "avenqo_voice_resolver"

PHONE_RESOLVER_SQL = """
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
    v_count integer;
    v_norm text;
BEGIN
    IF p_phone_number IS NULL OR btrim(p_phone_number) = '' THEN
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

    SELECT count(DISTINCT company_id) INTO v_count
    FROM voice_phone_numbers
    WHERE (phone_number = p_phone_number OR phone_number = v_norm)
      AND status = 'ACTIVE'
      AND provider = 'telnyx';

    IF v_count IS DISTINCT FROM 1 THEN
        RETURN NULL;
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


def _postgres(bind) -> bool:
    dialect = getattr(bind, "dialect", None)
    return dialect is not None and getattr(dialect, "name", None) == "postgresql"


def upgrade() -> None:
    bind = op.get_bind()
    if not _postgres(bind):
        return
    bind.execute(sa.text(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'avenqo_voice_resolver') THEN
            CREATE ROLE avenqo_voice_resolver
              NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION BYPASSRLS;
          END IF;
        END $$;
        """
    ))
    bind.execute(sa.text(
        "ALTER ROLE avenqo_voice_resolver WITH NOLOGIN NOSUPERUSER NOCREATEDB "
        "NOCREATEROLE NOINHERIT NOREPLICATION BYPASSRLS"
    ))
    bind.execute(sa.text("GRANT USAGE ON SCHEMA public TO avenqo_voice_resolver"))
    bind.execute(sa.text("GRANT SELECT ON TABLE public.voice_phone_numbers TO avenqo_voice_resolver"))
    bind.execute(sa.text("GRANT SELECT ON TABLE public.voice_calls TO avenqo_voice_resolver"))
    bind.execute(sa.text(PHONE_RESOLVER_SQL))
    bind.execute(sa.text(
        "ALTER FUNCTION public.resolve_voice_phone_number_tenant(text) OWNER TO avenqo_voice_resolver"
    ))
    bind.execute(sa.text(
        "ALTER FUNCTION public.resolve_voice_call_tenant(uuid, text) OWNER TO avenqo_voice_resolver"
    ))
    bind.execute(sa.text("GRANT EXECUTE ON FUNCTION public.resolve_voice_phone_number_tenant(text) TO avenqo_app"))
    bind.execute(sa.text("GRANT EXECUTE ON FUNCTION public.resolve_voice_call_tenant(uuid, text) TO avenqo_app"))


def downgrade() -> None:
    bind = op.get_bind()
    if not _postgres(bind):
        return
    bind.execute(sa.text(
        """
        DO $$
        DECLARE
          owner_name text;
        BEGIN
          SELECT r.rolname INTO owner_name
          FROM pg_class c
          JOIN pg_roles r ON c.relowner = r.oid
          WHERE c.relname = 'voice_phone_numbers';
          owner_name := COALESCE(owner_name, 'avenqo_owner');
          EXECUTE format(
            'ALTER FUNCTION public.resolve_voice_phone_number_tenant(text) OWNER TO %I',
            owner_name
          );
          EXECUTE format(
            'ALTER FUNCTION public.resolve_voice_call_tenant(uuid, text) OWNER TO %I',
            owner_name
          );
        END $$;
        """
    ))
