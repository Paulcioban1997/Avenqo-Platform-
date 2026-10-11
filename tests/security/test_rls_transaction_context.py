"""Verify transaction/pool isolation with a disposable non-superuser PostgreSQL login."""
import os
import secrets
from uuid import uuid4

import pytest
from psycopg2 import sql
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from backend.app.services.tenant_rls import apply_tenant_rls, set_rls_bypass


def test_tenant_context_survives_commit_rollback_without_pool_leakage():
    value = os.environ.get("AVENQO_ROTATION_TEST_ADMIN_URL")
    if not value:
        pytest.skip("Isolated PostgreSQL service required")
    url = make_url(value)
    assert os.environ.get("ENVIRONMENT") == "test"
    assert url.host in {"localhost", "127.0.0.1"} and url.database.startswith("rotation_test_")
    admin = create_engine(url, echo=False)
    suffix = uuid4().hex[:12]
    role, schema = "rls_" + suffix, "rls_" + suffix
    password = secrets.token_urlsafe(40)
    a, b = uuid4(), uuid4()
    api = None
    try:
        with admin.begin() as db:
            cur = db.connection.driver_connection.cursor()
            cur.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(sql.Identifier(role), sql.Literal(password)))
            cur.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            cur.execute(sql.SQL("CREATE TABLE {}.probe (company_id uuid PRIMARY KEY, marker text)").format(sql.Identifier(schema)))
            cur.execute(sql.SQL("INSERT INTO {}.probe VALUES (%s, 'a'), (%s, 'b')").format(sql.Identifier(schema)), (str(a), str(b)))
            cur.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(sql.Identifier(schema), sql.Identifier(role)))
            cur.execute(sql.SQL("GRANT SELECT, INSERT, UPDATE ON {}.probe TO {}").format(sql.Identifier(schema), sql.Identifier(role)))
            cur.execute(sql.SQL("ALTER TABLE {}.probe ENABLE ROW LEVEL SECURITY").format(sql.Identifier(schema)))
            cur.execute(sql.SQL("ALTER TABLE {}.probe FORCE ROW LEVEL SECURITY").format(sql.Identifier(schema)))
            cur.execute(sql.SQL("CREATE POLICY tenant ON {}.probe USING (current_setting('app.bypass_rls', true)='on' OR company_id=NULLIF(current_setting('app.current_company_id', true),'')::uuid)").format(sql.Identifier(schema)))
            cur.close()
        api = create_engine(url.set(username=role, password=password), echo=False, pool_size=1, max_overflow=0)
        query = text(f'SELECT marker FROM "{schema}".probe ORDER BY marker')
        with Session(api) as db:
            assert not db.execute(text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user")).scalar_one()
            apply_tenant_rls(db, a)
            assert list(db.scalars(query)) == ["a"]
            db.commit()
            assert list(db.scalars(query)) == ["a"]
            db.rollback()
            assert list(db.scalars(query)) == ["a"]
            db.execute(text(f'UPDATE "{schema}".probe SET marker=:marker'), {"marker":"a-updated"})
            db.commit()
            assert list(db.scalars(query)) == ["a-updated"]
            set_rls_bypass(db, enabled=True)
            assert len(list(db.scalars(query))) == 2
            db.commit()
            apply_tenant_rls(db, b)
            assert list(db.scalars(query)) == ["b"]
        # Same pooled connection must not retain tenant or privileged context.
        with api.connect() as db:
            assert list(db.scalars(query)) == []
        with Session(api) as db:
            apply_tenant_rls(db, b)
            assert list(db.scalars(query)) == ["b"]
    finally:
        if api:
            api.dispose()
        with admin.begin() as db:
            cur = db.connection.driver_connection.cursor()
            cur.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))
            cur.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))
            cur.close()
        admin.dispose()
