"""Rehearse Alembic 0060 FORCE RLS with avenqo_app LOGIN on isolated PostgreSQL.

Refuses Sandbox, Production, and any non-localhost host. Never prints passwords.
Never rewrites Railway DATABASE_URL. Never touches a live Sandbox copy.
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_PROBE_TABLES = (
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--admin-url",
        default=os.environ.get("AVENQO_ROTATION_TEST_ADMIN_URL", ""),
        help="Isolated localhost admin URL.",
    )
    args = parser.parse_args()
    environment = os.environ.get("ENVIRONMENT", "").strip().lower()
    if environment in {"sandbox", "production"}:
        print("Refused: rehearsal is isolated/test only.", file=sys.stderr)
        return 2
    admin_url = args.admin_url.strip()
    if not admin_url:
        print("AVENQO_ROTATION_TEST_ADMIN_URL or --admin-url is required.", file=sys.stderr)
        return 2

    from psycopg2 import sql
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url
    from sqlalchemy.orm import Session

    from backend.app.services.postgres_app_role import (
        APP_ROLE,
        application_database_url,
        ensure_application_roles,
        role_is_constrained,
    )
    from backend.app.services.tenant_rls import RLS_EXPANSION_0060, apply_force_rls_policies, apply_tenant_rls

    parsed = make_url(admin_url)
    if parsed.host not in {"localhost", "127.0.0.1"}:
        print("Refused: host is not isolated localhost.", file=sys.stderr)
        return 2

    app_password = secrets.token_urlsafe(32)
    tenant_a, tenant_b = uuid4(), uuid4()
    admin = create_engine(parsed)
    app_engine = None
    report = {
        "host_isolated": True,
        "tables_forced": 0,
        "app_direct_login": False,
        "session_user_is_app": False,
        "rls_hides_foreign_tenant": False,
        "empty_guc_sees_zero": False,
        "pooled_connection_does_not_leak": False,
        "app_cannot_disable_rls": False,
        "app_cannot_set_role_postgres": False,
        "login_disabled_after": False,
        "database_url_unchanged": True,
    }
    try:
        with admin.begin() as connection:
            ensure_application_roles(connection)
            if not role_is_constrained(connection, APP_ROLE):
                print("avenqo_app is not constrained.", file=sys.stderr)
                return 1
            connection.execute(text(_TENANT_FN))
            for table in _PROBE_TABLES:
                connection.execute(text(f'DROP TABLE IF EXISTS "{table}" CASCADE'))
                connection.execute(text(f'CREATE TABLE "{table}" (company_id uuid NOT NULL, marker text NOT NULL)'))
                connection.execute(
                    text(f'INSERT INTO "{table}" VALUES (:a, :am), (:b, :bm)'),
                    {"a": tenant_a, "am": f"{table}-a", "b": tenant_b, "bm": f"{table}-b"},
                )
            apply_force_rls_policies(connection, RLS_EXPANSION_0060)
            for table in _PROBE_TABLES:
                connection.execute(text(f'GRANT SELECT ON "{table}" TO {APP_ROLE}'))
            cursor = connection.connection.driver_connection.cursor()
            cursor.execute(
                sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}").format(
                    sql.Identifier(APP_ROLE),
                    sql.Literal(app_password),
                )
            )
            cursor.close()

        with admin.begin() as connection:
            forced = connection.execute(
                text(
                    "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = 'public' AND c.relname = ANY(:tables) AND c.relforcerowsecurity"
                ),
                {"tables": list(_PROBE_TABLES)},
            ).scalar_one()
            report["tables_forced"] = int(forced)

        app_engine = create_engine(
            application_database_url(admin_url, app_password),
            echo=False,
            pool_size=1,
            max_overflow=0,
            pool_reset_on_return="rollback",
        )
        with app_engine.connect() as connection:
            row = connection.execute(
                text("SELECT current_user, session_user FROM pg_roles WHERE rolname = current_user")
            ).one()
            report["app_direct_login"] = True
            report["session_user_is_app"] = row[0] == APP_ROLE and row[1] == APP_ROLE

        query = text('SELECT marker FROM "predictions" ORDER BY marker')
        with app_engine.begin() as connection:
            connection.execute(
                text(
                    "SELECT set_config('app.bypass_rls','off',true), "
                    "set_config('app.current_company_id',:cid,true)"
                ),
                {"cid": str(tenant_a)},
            )
            a_rows = list(connection.execute(query).scalars())
        with app_engine.begin() as connection:
            connection.execute(
                text(
                    "SELECT set_config('app.bypass_rls','off',true), "
                    "set_config('app.current_company_id',:cid,true)"
                ),
                {"cid": str(tenant_b)},
            )
            b_rows = list(connection.execute(query).scalars())
        report["rls_hides_foreign_tenant"] = a_rows == ["predictions-a"] and b_rows == ["predictions-b"]

        with app_engine.begin() as connection:
            connection.execute(
                text("SELECT set_config('app.bypass_rls','off',true), set_config('app.current_company_id','',true)")
            )
            empty = connection.execute(text('SELECT count(*) FROM "predictions"')).scalar_one()
        report["empty_guc_sees_zero"] = empty == 0

        with Session(app_engine) as session:
            apply_tenant_rls(session, tenant_a)
            assert list(session.scalars(query)) == ["predictions-a"]
            session.commit()
        with app_engine.connect() as connection:
            leaked = list(connection.scalars(query))
        report["pooled_connection_does_not_leak"] = leaked == []

        try:
            with app_engine.begin() as connection:
                connection.execute(text('ALTER TABLE "predictions" DISABLE ROW LEVEL SECURITY'))
            report["app_cannot_disable_rls"] = False
        except Exception:
            report["app_cannot_disable_rls"] = True

        try:
            with app_engine.begin() as connection:
                connection.execute(text("SET ROLE postgres"))
            report["app_cannot_set_role_postgres"] = False
        except Exception:
            report["app_cannot_set_role_postgres"] = True
    finally:
        if app_engine is not None:
            app_engine.dispose()
        with admin.begin() as connection:
            for table in _PROBE_TABLES:
                connection.execute(text(f'DROP TABLE IF EXISTS "{table}" CASCADE'))
            cursor = connection.connection.driver_connection.cursor()
            cursor.execute(sql.SQL("ALTER ROLE {} NOLOGIN PASSWORD NULL").format(sql.Identifier(APP_ROLE)))
            cursor.close()
            can_login = connection.execute(
                text("SELECT rolcanlogin FROM pg_roles WHERE rolname=:n"), {"n": APP_ROLE}
            ).scalar_one()
            report["login_disabled_after"] = can_login is False
        admin.dispose()

    failed = [key for key, value in report.items() if value is False]
    print(" ".join(f"{key}={str(value).lower()}" for key, value in report.items()))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
