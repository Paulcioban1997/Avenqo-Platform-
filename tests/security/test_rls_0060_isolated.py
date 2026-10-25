"""Rehearse Alembic 0060 FORCE RLS as avenqo_app LOGIN on isolated PostgreSQL only."""

from __future__ import annotations

import secrets
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from tests.security.isolated_postgres import require_isolated_admin_url

from backend.app.services.postgres_app_role import (
    APP_ROLE,
    application_database_url,
    ensure_application_roles,
    role_is_constrained,
)
from backend.app.services.tenant_rls import (
    RLS_EXPANSION_0060,
    apply_force_rls_policies,
    apply_tenant_rls,
)

_0060_PROBE_TABLES = (
    "tenant_ai_credit_balances",
    "voice_central_sessions",
    "normalized_commerce_records",
    "company_modules",
    "predictions",
)

_TENANT_FN = """
CREATE OR REPLACE FUNCTION avenqo_tenant_id() RETURNS uuid AS $$
BEGIN
  RETURN NULLIF(current_setting('app.current_company_id', true), '')::uuid;
EXCEPTION WHEN others THEN
  RETURN NULL;
END;
$$ LANGUAGE plpgsql STABLE;
"""


def test_0060_force_rls_with_avenqo_app_login_hides_foreign_tenants_and_blocks_bypass_ddl():
    from psycopg2 import sql

    url = require_isolated_admin_url()
    admin = create_engine(url)
    tenant_a, tenant_b = uuid4(), uuid4()
    app_password = secrets.token_urlsafe(32)
    app_engine = None
    try:
        with admin.begin() as connection:
            ensure_application_roles(connection)
            assert role_is_constrained(connection, APP_ROLE)
            connection.execute(text(_TENANT_FN))
            for table in _0060_PROBE_TABLES:
                connection.execute(text(f'DROP TABLE IF EXISTS "{table}" CASCADE'))
                connection.execute(
                    text(f'CREATE TABLE "{table}" (company_id uuid NOT NULL, marker text NOT NULL)')
                )
                connection.execute(
                    text(f'INSERT INTO "{table}" VALUES (:a, :am), (:b, :bm)'),
                    {"a": tenant_a, "am": f"{table}-a", "b": tenant_b, "bm": f"{table}-b"},
                )
            apply_force_rls_policies(connection, RLS_EXPANSION_0060)
            for table in _0060_PROBE_TABLES:
                connection.execute(text(f'GRANT SELECT ON "{table}" TO avenqo_app'))
            cursor = connection.connection.driver_connection.cursor()
            cursor.execute(
                sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}").format(
                    sql.Identifier(APP_ROLE),
                    sql.Literal(app_password),
                )
            )
            cursor.close()

        with admin.begin() as connection:
            for table in _0060_PROBE_TABLES:
                forced = connection.execute(
                    text(
                        "SELECT c.relforcerowsecurity FROM pg_class c "
                        "JOIN pg_namespace n ON n.oid = c.relnamespace "
                        "WHERE n.nspname = 'public' AND c.relname = :table"
                    ),
                    {"table": table},
                ).scalar_one()
                assert forced is True
                policy = connection.execute(
                    text(
                        "SELECT polname FROM pg_policy "
                        "JOIN pg_class c ON c.oid = pg_policy.polrelid "
                        "WHERE c.relname = :table AND polname = :policy"
                    ),
                    {"table": table, "policy": f"{table}_tenant_isolation"},
                ).scalar_one()
                assert policy == f"{table}_tenant_isolation"

        app_engine = create_engine(
            application_database_url(str(url), app_password),
            echo=False,
            pool_size=1,
            max_overflow=0,
            pool_reset_on_return="rollback",
        )
        with app_engine.connect() as connection:
            row = connection.execute(
                text("SELECT current_user, session_user, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
            ).one()
            assert row[0] == APP_ROLE
            assert row[1] == APP_ROLE
            assert row[2] is False
            assert row[3] is False

        for table in _0060_PROBE_TABLES:
            query = text(f'SELECT marker FROM "{table}" ORDER BY marker')
            with app_engine.begin() as connection:
                connection.execute(
                    text(
                        "SELECT set_config('app.bypass_rls','off',true), "
                        "set_config('app.current_company_id',:cid,true)"
                    ),
                    {"cid": str(tenant_a)},
                )
                assert list(connection.execute(query).scalars()) == [f"{table}-a"]
            with app_engine.begin() as connection:
                connection.execute(
                    text(
                        "SELECT set_config('app.bypass_rls','off',true), "
                        "set_config('app.current_company_id',:cid,true)"
                    ),
                    {"cid": str(tenant_b)},
                )
                assert list(connection.execute(query).scalars()) == [f"{table}-b"]
            with app_engine.begin() as connection:
                connection.execute(
                    text(
                        "SELECT set_config('app.bypass_rls','off',true), "
                        "set_config('app.current_company_id','',true)"
                    )
                )
                assert connection.execute(text(f'SELECT count(*) FROM "{table}"')).scalar_one() == 0

        query = text('SELECT marker FROM "predictions" ORDER BY marker')
        with Session(app_engine) as session:
            apply_tenant_rls(session, tenant_a)
            assert list(session.scalars(query)) == ["predictions-a"]
            session.commit()
        with app_engine.connect() as connection:
            assert list(connection.scalars(query)) == []
        with Session(app_engine) as session:
            apply_tenant_rls(session, tenant_b)
            assert list(session.scalars(query)) == ["predictions-b"]

        disabled = False
        try:
            with app_engine.begin() as connection:
                connection.execute(text('ALTER TABLE "predictions" DISABLE ROW LEVEL SECURITY'))
            disabled = True
        except Exception:
            disabled = False
        assert disabled is False

        escalated = False
        try:
            with app_engine.begin() as connection:
                connection.execute(text("SET ROLE postgres"))
            escalated = True
        except Exception:
            escalated = False
        assert escalated is False
    finally:
        if app_engine is not None:
            app_engine.dispose()
        with admin.begin() as connection:
            for table in _0060_PROBE_TABLES:
                connection.execute(text(f'DROP TABLE IF EXISTS "{table}" CASCADE'))
            cursor = connection.connection.driver_connection.cursor()
            cursor.execute(sql.SQL("ALTER ROLE {} NOLOGIN PASSWORD NULL").format(sql.Identifier(APP_ROLE)))
            cursor.close()
        admin.dispose()
