"""Prove avenqo_app is constrained and isolates two tenants. Isolated PostgreSQL only."""

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
import os

from backend.app.services.postgres_app_role import APP_ROLE, MIGRATE_ROLE, OWNER_ROLE, ensure_application_roles, role_is_constrained


@pytest.mark.skipif(not os.getenv("AVENQO_ROTATION_TEST_ADMIN_URL"), reason="Isolated PostgreSQL required")
def test_app_role_force_rls_hides_foreign_tenant_rows():
    url = make_url(os.environ["AVENQO_ROTATION_TEST_ADMIN_URL"])
    assert os.environ.get("ENVIRONMENT") == "test"
    assert url.host in {"localhost", "127.0.0.1"}
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
