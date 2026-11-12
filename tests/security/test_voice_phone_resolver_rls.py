"""Dedicated inbound numbers must resolve under FORCE RLS without opening the app role."""

from uuid import uuid4

from sqlalchemy import create_engine, text

from tests.security.isolated_postgres import require_isolated_admin_url


def test_phone_resolver_sees_binding_when_table_owner_cannot_bypass_force_rls():
    url = require_isolated_admin_url()
    admin = create_engine(url)
    company_a = uuid4()
    company_b = uuid4()
    phone = "+14386075438"
    with admin.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS voice_phone_numbers"))
        connection.execute(text("DROP FUNCTION IF EXISTS public.resolve_voice_phone_number_tenant(text)"))
        connection.execute(text(
            """
            DO $$
            BEGIN
              IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'avenqo_owner') THEN
                CREATE ROLE avenqo_owner NOLOGIN NOBYPASSRLS;
              END IF;
              IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'avenqo_app') THEN
                CREATE ROLE avenqo_app NOLOGIN NOBYPASSRLS;
              END IF;
              IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'avenqo_voice_resolver') THEN
                CREATE ROLE avenqo_voice_resolver NOLOGIN BYPASSRLS;
              END IF;
            END $$;
            """
        ))
        connection.execute(text(
            "ALTER ROLE avenqo_owner WITH NOLOGIN NOSUPERUSER NOBYPASSRLS"
        ))
        connection.execute(text(
            "ALTER ROLE avenqo_app WITH NOLOGIN NOSUPERUSER NOBYPASSRLS"
        ))
        connection.execute(text(
            "ALTER ROLE avenqo_voice_resolver WITH NOLOGIN NOSUPERUSER BYPASSRLS"
        ))
        connection.execute(text(
            """
            CREATE TABLE voice_phone_numbers (
              company_id uuid NOT NULL,
              phone_number text NOT NULL,
              status text NOT NULL,
              provider text NOT NULL
            )
            """
        ))
        connection.execute(text("ALTER TABLE voice_phone_numbers OWNER TO avenqo_owner"))
        connection.execute(text("ALTER TABLE voice_phone_numbers ENABLE ROW LEVEL SECURITY"))
        connection.execute(text("ALTER TABLE voice_phone_numbers FORCE ROW LEVEL SECURITY"))
        connection.execute(text(
            """
            CREATE POLICY voice_phone_numbers_tenant_isolation ON voice_phone_numbers
            USING (company_id::text = current_setting('app.current_company_id', true))
            """
        ))
        connection.execute(text("GRANT SELECT ON voice_phone_numbers TO avenqo_app"))
        connection.execute(text("GRANT SELECT ON voice_phone_numbers TO avenqo_voice_resolver"))
        connection.execute(
            text(
                "INSERT INTO voice_phone_numbers VALUES (:company, :phone, 'ACTIVE', 'telnyx')"
            ),
            {"company": company_a, "phone": phone},
        )
        connection.execute(text(
            """
            CREATE OR REPLACE FUNCTION public.resolve_voice_phone_number_tenant(p_phone_number text)
            RETURNS uuid
            LANGUAGE sql
            SECURITY DEFINER
            STABLE
            SET search_path = public, pg_temp
            AS $$
              SELECT company_id FROM voice_phone_numbers
              WHERE phone_number = p_phone_number AND status = 'ACTIVE' AND provider = 'telnyx'
              LIMIT 1
            $$;
            """
        ))
        connection.execute(text(
            "ALTER FUNCTION public.resolve_voice_phone_number_tenant(text) OWNER TO avenqo_owner"
        ))
        connection.execute(text(
            "GRANT EXECUTE ON FUNCTION public.resolve_voice_phone_number_tenant(text) TO avenqo_app"
        ))
        connection.execute(text("SET ROLE avenqo_app"))
        hidden = connection.execute(
            text("SELECT public.resolve_voice_phone_number_tenant(:phone)"),
            {"phone": phone},
        ).scalar()
        connection.execute(text("RESET ROLE"))
        assert hidden is None

        import importlib
        migration = importlib.import_module("alembic.versions.0077_voice_resolver_bypass_rls")
        connection.execute(text(migration.PHONE_RESOLVER_SQL))
        connection.execute(text(
            "ALTER FUNCTION public.resolve_voice_phone_number_tenant(text) OWNER TO avenqo_voice_resolver"
        ))
        connection.execute(text(
            "GRANT EXECUTE ON FUNCTION public.resolve_voice_phone_number_tenant(text) TO avenqo_app"
        ))
        connection.execute(text("SET ROLE avenqo_app"))
        found = connection.execute(
            text("SELECT public.resolve_voice_phone_number_tenant(:phone)"),
            {"phone": phone},
        ).scalar()
        connection.execute(text("RESET ROLE"))
        assert found == company_a

        connection.execute(text("SET ROLE avenqo_app"))
        visible = connection.execute(text("SELECT count(*) FROM voice_phone_numbers")).scalar()
        connection.execute(text("RESET ROLE"))
        assert visible == 0

        connection.execute(
            text("INSERT INTO voice_phone_numbers VALUES (:company, :phone, 'ACTIVE', 'telnyx')"),
            {"company": company_b, "phone": phone},
        )
        ambiguous = connection.execute(text(
            "SELECT public.resolve_voice_phone_number_tenant(:phone)"
        ), {"phone": phone}).scalar()
        assert ambiguous is None
        connection.execute(text("DROP TABLE voice_phone_numbers"))
        connection.execute(text("DROP FUNCTION public.resolve_voice_phone_number_tenant(text)"))
