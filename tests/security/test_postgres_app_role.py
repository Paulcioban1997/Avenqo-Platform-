"""Prove avenqo_app is constrained and isolates two tenants. Isolated PostgreSQL only."""

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

from backend.app.services.postgres_app_role import (
    APP_ROLE,
    MIGRATE_ROLE,
    OWNER_ROLE,
    application_database_url,
    ensure_application_roles,
    role_is_constrained,
)
from tests.security.isolated_postgres import require_isolated_admin_url


def test_app_role_force_rls_hides_foreign_tenant_rows():
    url = require_isolated_admin_url()
    from sqlalchemy import create_engine

    admin = create_engine(url)
    a, b = uuid4(), uuid4()
    try:
        with admin.begin() as connection:
            ensure_application_roles(connection)
            assert role_is_constrained(connection, APP_ROLE)
            assert role_is_constrained(connection, MIGRATE_ROLE)
            assert role_is_constrained(connection, OWNER_ROLE)
            assert connection.execute(text("SELECT rolcanlogin FROM pg_roles WHERE rolname=:n"), {"n": APP_ROLE}).scalar_one() is False
            assert connection.execute(text("SELECT has_schema_privilege('avenqo_migrate', 'public', 'CREATE')")).scalar_one() is True
            assert connection.execute(text("SELECT has_schema_privilege('avenqo_app', 'public', 'CREATE')")).scalar_one() is False
            connection.execute(text("DROP TABLE IF EXISTS billing_invoices_probe"))
            connection.execute(text("CREATE TABLE billing_invoices_probe (company_id uuid NOT NULL, marker text NOT NULL)"))
            connection.execute(
                text("INSERT INTO billing_invoices_probe VALUES (:a, 'invoice-a'), (:b, 'invoice-b')"),
                {"a": a, "b": b},
            )
            connection.execute(text("ALTER TABLE billing_invoices_probe ENABLE ROW LEVEL SECURITY"))
            connection.execute(text("ALTER TABLE billing_invoices_probe FORCE ROW LEVEL SECURITY"))
            connection.execute(text("DROP POLICY IF EXISTS billing_invoices_probe_tenant ON billing_invoices_probe"))
            connection.execute(
                text(
                    """
                    CREATE POLICY billing_invoices_probe_tenant ON billing_invoices_probe
                    USING (
                      current_setting('app.bypass_rls', true) = 'on'
                      OR company_id = NULLIF(current_setting('app.current_company_id', true), '')::uuid
                    )
                    """
                )
            )
            connection.execute(text("GRANT SELECT ON billing_invoices_probe TO avenqo_app"))
        with admin.begin() as connection:
            connection.execute(text("SET LOCAL ROLE avenqo_app"))
            connection.execute(
                text("SELECT set_config('app.bypass_rls','off',true), set_config('app.current_company_id',:cid,true)"),
                {"cid": str(a)},
            )
            markers = list(connection.execute(text("SELECT marker FROM billing_invoices_probe ORDER BY marker")).scalars())
            assert markers == ["invoice-a"]
        with admin.begin() as connection:
            connection.execute(text("SET LOCAL ROLE avenqo_app"))
            connection.execute(
                text("SELECT set_config('app.bypass_rls','off',true), set_config('app.current_company_id',:cid,true)"),
                {"cid": str(b)},
            )
            markers = list(connection.execute(text("SELECT marker FROM billing_invoices_probe ORDER BY marker")).scalars())
            assert markers == ["invoice-b"]
        with admin.begin() as connection:
            connection.execute(text("SET LOCAL ROLE avenqo_app"))
            connection.execute(text("SELECT set_config('app.bypass_rls','off',true), set_config('app.current_company_id','',true)"))
            assert connection.execute(text("SELECT count(*) FROM billing_invoices_probe")).scalar_one() == 0
    finally:
        with admin.begin() as connection:
            connection.execute(text("DROP TABLE IF EXISTS billing_invoices_probe"))
        admin.dispose()


def test_application_database_url_rejects_remote_hosts():
    remote = (
        make_url("postgresql+psycopg2://127.0.0.1:5432/rotation_test_ci")
        .set(username="postgres", password="test-only-password", host="postgres.railway.internal")
        .render_as_string(hide_password=False)
    )
    isolated = (
        make_url("postgresql+psycopg2://127.0.0.1:5432/rotation_test_ci")
        .set(username="postgres", password="test-only-password", host="127.0.0.1")
        .render_as_string(hide_password=False)
    )
    with pytest.raises(ValueError, match="isolated-host only"):
        application_database_url(remote, "test-only-password")
    local = application_database_url(isolated, "test-only-password")
    parsed = make_url(local)
    assert parsed.username == APP_ROLE
    assert parsed.host == "127.0.0.1"
    assert parsed.password == "test-only-password"


def test_direct_app_role_login_enforces_rls_and_blocks_ddl():
    """Connect as avenqo_app (session_user), not SET ROLE from a superuser."""
    import secrets

    from psycopg2 import sql
    from sqlalchemy import create_engine

    url = require_isolated_admin_url()
    admin = create_engine(url)
    a, b = uuid4(), uuid4()
    app_password = secrets.token_urlsafe(32)
    migrate_password = secrets.token_urlsafe(32)
    app_engine = migrate_engine = None
    try:
        with admin.begin() as connection:
            ensure_application_roles(connection)
            connection.execute(text("DROP TABLE IF EXISTS app_role_login_probe"))
            connection.execute(text("DROP TABLE IF EXISTS migrate_created_probe"))
            connection.execute(text("CREATE TABLE app_role_login_probe (company_id uuid NOT NULL, marker text NOT NULL)"))
            connection.execute(
                text("INSERT INTO app_role_login_probe VALUES (:a, 'invoice-a'), (:b, 'invoice-b')"),
                {"a": a, "b": b},
            )
            connection.execute(text("ALTER TABLE app_role_login_probe ENABLE ROW LEVEL SECURITY"))
            connection.execute(text("ALTER TABLE app_role_login_probe FORCE ROW LEVEL SECURITY"))
            connection.execute(text("DROP POLICY IF EXISTS app_role_login_probe_tenant ON app_role_login_probe"))
            connection.execute(
                text(
                    """
                    CREATE POLICY app_role_login_probe_tenant ON app_role_login_probe
                    USING (
                      current_setting('app.bypass_rls', true) = 'on'
                      OR company_id = NULLIF(current_setting('app.current_company_id', true), '')::uuid
                    )
                    """
                )
            )
            connection.execute(text("GRANT SELECT ON app_role_login_probe TO avenqo_app"))
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

        app_engine = create_engine(application_database_url(admin_url, app_password), echo=False)
        migrate_engine = create_engine(
            application_database_url(admin_url, migrate_password, role=MIGRATE_ROLE),
            echo=False,
        )

        with app_engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT current_user, session_user, rolsuper, rolbypassrls, rolcanlogin "
                    "FROM pg_roles WHERE rolname = current_user"
                )
            ).one()
            assert row[0] == APP_ROLE
            assert row[1] == APP_ROLE
            assert row[2] is False
            assert row[3] is False
            assert row[4] is True

        with app_engine.begin() as connection:
            connection.execute(
                text("SELECT set_config('app.bypass_rls','off',true), set_config('app.current_company_id',:cid,true)"),
                {"cid": str(a)},
            )
            markers = list(connection.execute(text("SELECT marker FROM app_role_login_probe ORDER BY marker")).scalars())
            assert markers == ["invoice-a"]

        with app_engine.begin() as connection:
            connection.execute(
                text("SELECT set_config('app.bypass_rls','off',true), set_config('app.current_company_id',:cid,true)"),
                {"cid": str(b)},
            )
            markers = list(connection.execute(text("SELECT marker FROM app_role_login_probe ORDER BY marker")).scalars())
            assert markers == ["invoice-b"]

        with app_engine.begin() as connection:
            connection.execute(text("SELECT set_config('app.bypass_rls','off',true), set_config('app.current_company_id','',true)"))
            assert connection.execute(text("SELECT count(*) FROM app_role_login_probe")).scalar_one() == 0

        with app_engine.begin() as connection:
            connection.execute(text("SELECT set_config('app.bypass_rls','on',true), set_config('app.current_company_id','',true)"))
            assert connection.execute(text("SELECT count(*) FROM app_role_login_probe")).scalar_one() == 2

        app_created_table = False
        try:
            with app_engine.begin() as connection:
                connection.execute(text("CREATE TABLE app_role_should_not_exist (id integer)"))
            app_created_table = True
        except Exception:
            app_created_table = False
        assert app_created_table is False

        escalated = False
        try:
            with app_engine.begin() as connection:
                connection.execute(text("SET ROLE postgres"))
            escalated = True
        except Exception:
            escalated = False
        assert escalated is False

        with migrate_engine.begin() as connection:
            assert connection.execute(text("SELECT current_user")).scalar_one() == MIGRATE_ROLE
            connection.execute(text("CREATE TABLE migrate_created_probe (id integer PRIMARY KEY, marker text)"))
            connection.execute(text("INSERT INTO migrate_created_probe VALUES (1, 'from-migrate')"))

        with app_engine.begin() as connection:
            assert connection.execute(text("SELECT marker FROM migrate_created_probe")).scalar_one() == "from-migrate"

        app_disabled_rls = False
        try:
            with app_engine.begin() as connection:
                connection.execute(text("ALTER TABLE app_role_login_probe DISABLE ROW LEVEL SECURITY"))
            app_disabled_rls = True
        except Exception:
            app_disabled_rls = False
        assert app_disabled_rls is False
    finally:
        if app_engine is not None:
            app_engine.dispose()
        if migrate_engine is not None:
            migrate_engine.dispose()
        with admin.begin() as connection:
            connection.execute(text("DROP TABLE IF EXISTS app_role_login_probe"))
            connection.execute(text("DROP TABLE IF EXISTS migrate_created_probe"))
            connection.execute(text("DROP TABLE IF EXISTS app_role_should_not_exist"))
            cursor = connection.connection.driver_connection.cursor()
            cursor.execute(sql.SQL("ALTER ROLE {} NOLOGIN PASSWORD NULL").format(sql.Identifier(APP_ROLE)))
            cursor.execute(sql.SQL("ALTER ROLE {} NOLOGIN PASSWORD NULL").format(sql.Identifier(MIGRATE_ROLE)))
            cursor.close()
        admin.dispose()
