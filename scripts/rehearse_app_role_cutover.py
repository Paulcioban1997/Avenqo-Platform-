"""Rehearse API/worker/migrate cutover to avenqo_app on an isolated PostgreSQL only.

Refuses Sandbox, Production, and any non-localhost host. Never prints passwords.
Never rewrites Railway DATABASE_URL.
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--admin-url",
        default=os.environ.get("AVENQO_ROTATION_TEST_ADMIN_URL", ""),
        help="Isolated localhost admin URL. Defaults to AVENQO_ROTATION_TEST_ADMIN_URL.",
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

    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url
    from psycopg2 import sql

    from backend.app.services.postgres_app_role import (
        APP_ROLE,
        MIGRATE_ROLE,
        application_database_url,
        ensure_application_roles,
        role_is_constrained,
    )

    parsed = make_url(admin_url)
    if parsed.host not in {"localhost", "127.0.0.1"}:
        print("Refused: host is not isolated localhost.", file=sys.stderr)
        return 2

    app_password = secrets.token_urlsafe(32)
    migrate_password = secrets.token_urlsafe(32)
    tenant_a, tenant_b = uuid4(), uuid4()
    admin = create_engine(parsed)
    app_engine = migrate_engine = None
    report = {
        "host_isolated": True,
        "app_direct_login": False,
        "session_user_is_app": False,
        "rls_hides_foreign_tenant": False,
        "worker_guc_bypass_sees_all": False,
        "app_cannot_create_table": False,
        "app_cannot_set_role_postgres": False,
        "migrate_can_create_table": False,
        "app_reads_migrate_table": False,
        "login_disabled_after": False,
        "database_url_unchanged": True,
        "nine_connectors": (
            "shopify", "woocommerce", "etsy", "google_calendar", "outlook_calendar",
            "stripe", "telnyx", "openai", "internal_commerce_scheduler",
        ),
    }
    try:
        with admin.begin() as connection:
            ensure_application_roles(connection)
            if not all(role_is_constrained(connection, name) for name in (APP_ROLE, MIGRATE_ROLE)):
                print("Roles are not constrained.", file=sys.stderr)
                return 1
            connection.execute(text("DROP TABLE IF EXISTS cutover_rehearsal_probe"))
            connection.execute(text("CREATE TABLE cutover_rehearsal_probe (company_id uuid NOT NULL, marker text NOT NULL)"))
            connection.execute(
                text("INSERT INTO cutover_rehearsal_probe VALUES (:a, 'a'), (:b, 'b')"),
                {"a": tenant_a, "b": tenant_b},
            )
            connection.execute(text("ALTER TABLE cutover_rehearsal_probe ENABLE ROW LEVEL SECURITY"))
            connection.execute(text("ALTER TABLE cutover_rehearsal_probe FORCE ROW LEVEL SECURITY"))
            connection.execute(
                text(
                    """
                    CREATE POLICY cutover_rehearsal_probe_tenant ON cutover_rehearsal_probe
                    USING (
                      current_setting('app.bypass_rls', true) = 'on'
                      OR company_id = NULLIF(current_setting('app.current_company_id', true), '')::uuid
                    )
                    """
                )
            )
            connection.execute(text("GRANT SELECT ON cutover_rehearsal_probe TO avenqo_app"))
            cursor = connection.connection.driver_connection.cursor()
            cursor.execute(
                sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}").format(
                    sql.Identifier(APP_ROLE),
                    sql.Literal(app_password),
                )
            )
            cursor.execute(
                sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}").format(
                    sql.Identifier(MIGRATE_ROLE),
                    sql.Literal(migrate_password),
                )
            )
            cursor.close()

        app_engine = create_engine(application_database_url(admin_url, app_password))
        migrate_engine = create_engine(
            application_database_url(admin_url, migrate_password, role=MIGRATE_ROLE)
        )
        with app_engine.connect() as connection:
            current_user, session_user = connection.execute(
                text("SELECT current_user, session_user")
            ).one()
            report["app_direct_login"] = current_user == APP_ROLE
            report["session_user_is_app"] = session_user == APP_ROLE
        with app_engine.begin() as connection:
            connection.execute(
                text("SELECT set_config('app.bypass_rls','off',true), set_config('app.current_company_id',:cid,true)"),
                {"cid": str(tenant_a)},
            )
            markers = list(connection.execute(text("SELECT marker FROM cutover_rehearsal_probe")).scalars())
            report["rls_hides_foreign_tenant"] = markers == ["a"]
        with app_engine.begin() as connection:
            connection.execute(
                text("SELECT set_config('app.bypass_rls','on',true), set_config('app.current_company_id','',true)")
            )
            report["worker_guc_bypass_sees_all"] = (
                connection.execute(text("SELECT count(*) FROM cutover_rehearsal_probe")).scalar_one() == 2
            )
        try:
            with app_engine.begin() as connection:
                connection.execute(text("CREATE TABLE cutover_app_should_not (id integer)"))
        except Exception:
            report["app_cannot_create_table"] = True
        try:
            with app_engine.begin() as connection:
                connection.execute(text("SET ROLE postgres"))
        except Exception:
            report["app_cannot_set_role_postgres"] = True
        with migrate_engine.begin() as connection:
            connection.execute(text("CREATE TABLE cutover_migrate_probe (id integer PRIMARY KEY, marker text)"))
            connection.execute(text("INSERT INTO cutover_migrate_probe VALUES (1, 'from-migrate')"))
            report["migrate_can_create_table"] = True
        with app_engine.begin() as connection:
            report["app_reads_migrate_table"] = (
                connection.execute(text("SELECT marker FROM cutover_migrate_probe")).scalar_one() == "from-migrate"
            )
    finally:
        if app_engine is not None:
            app_engine.dispose()
        if migrate_engine is not None:
            migrate_engine.dispose()
        with admin.begin() as connection:
            connection.execute(text("DROP TABLE IF EXISTS cutover_rehearsal_probe"))
            connection.execute(text("DROP TABLE IF EXISTS cutover_migrate_probe"))
            connection.execute(text("DROP TABLE IF EXISTS cutover_app_should_not"))
            cursor = connection.connection.driver_connection.cursor()
            cursor.execute(sql.SQL("ALTER ROLE {} NOLOGIN PASSWORD NULL").format(sql.Identifier(APP_ROLE)))
            cursor.execute(sql.SQL("ALTER ROLE {} NOLOGIN PASSWORD NULL").format(sql.Identifier(MIGRATE_ROLE)))
            cursor.close()
            report["login_disabled_after"] = (
                connection.execute(
                    text("SELECT rolcanlogin FROM pg_roles WHERE rolname=:n"),
                    {"n": APP_ROLE},
                ).scalar_one()
                is False
            )
        admin.dispose()

    failed = [name for name, ok in report.items() if ok is False]
    print(" ".join(f"{name}={str(value).lower()}" for name, value in report.items()))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
