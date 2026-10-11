"""Exercise dual-login transition only in an isolated local/CI PostgreSQL database."""
import os
import secrets
from uuid import uuid4
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from psycopg2 import sql


def test_new_login_preserves_data_then_old_login_is_effectively_revoked():
    value = os.environ.get("AVENQO_ROTATION_TEST_ADMIN_URL")
    if not value:
        pytest.skip("Isolated PostgreSQL test service not available")
    url = make_url(value)
    assert os.environ.get("ENVIRONMENT") == "test"
    assert url.host in {"localhost", "127.0.0.1"} and url.database.startswith("rotation_test_")
    admin = create_engine(url, echo=False)
    suffix = uuid4().hex[:12]; old = "old_" + suffix; new = "new_" + suffix; schema = "rotation_" + suffix
    owner = "owner_" + suffix; migrator = "migrator_" + suffix
    old_password, new_password = (secrets.token_urlsafe(40) for _ in range(2))
    migration_password = secrets.token_urlsafe(40)
    old_engine = new_engine = migration_engine = None
    try:
        with admin.begin() as conn:
            cursor = conn.connection.driver_connection.cursor()
            cursor.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(owner)))
            for name, password in ((old, old_password), (new, new_password), (migrator, migration_password)):
                cursor.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(sql.Identifier(name), sql.Literal(password)))
            for member in (old, migrator):
                cursor.execute(sql.SQL("GRANT {} TO {}").format(sql.Identifier(owner), sql.Identifier(member)))
            cursor.execute(sql.SQL("CREATE SCHEMA {} AUTHORIZATION {}").format(sql.Identifier(schema), sql.Identifier(owner)))
            cursor.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(owner)))
            cursor.execute(sql.SQL("CREATE TABLE {}.rotation_probe (id integer PRIMARY KEY, marker text)").format(sql.Identifier(schema)))
            cursor.execute(sql.SQL("INSERT INTO {}.rotation_probe VALUES (1, 'preserved')").format(sql.Identifier(schema)))
            cursor.execute("RESET ROLE")
            cursor.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(sql.Identifier(schema), sql.Identifier(new)))
            cursor.execute(sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {} TO {}").format(sql.Identifier(schema), sql.Identifier(new)))
            cursor.close()
        old_engine = create_engine(url.set(username=old, password=old_password), echo=False)
        new_engine = create_engine(url.set(username=new, password=new_password), echo=False, pool_pre_ping=True)
        migration_engine = create_engine(url.set(username=migrator, password=migration_password), echo=False)
        with migration_engine.begin() as conn:
            conn.exec_driver_sql(f'SET ROLE "{owner}"')
            conn.exec_driver_sql(f'ALTER TABLE "{schema}".rotation_probe ADD COLUMN migration_verified boolean DEFAULT true')
        with old_engine.connect() as conn:
            assert conn.execute(text(f'SELECT marker FROM "{schema}".rotation_probe WHERE id=1')).scalar() == "preserved"
        with new_engine.begin() as conn:
            assert conn.execute(text(f'SELECT marker FROM "{schema}".rotation_probe WHERE id=1')).scalar() == "preserved"
            conn.execute(text(f'INSERT INTO "{schema}".rotation_probe VALUES (2, :marker)'), {"marker": "new-login-write"})
        # Old login remains valid during transition, then is revoked only in this disposable fixture.
        with admin.begin() as conn:
            cursor = conn.connection.driver_connection.cursor()
            cursor.execute(sql.SQL("ALTER ROLE {} NOLOGIN PASSWORD NULL").format(sql.Identifier(old))); cursor.close()
        old_engine.dispose()
        try:
            with old_engine.connect():
                authenticated = True
        except Exception:
            authenticated = False  # Never surface authentication error text/connection details.
        assert not authenticated
        with new_engine.connect() as conn:
            assert conn.execute(text(f'SELECT count(*) FROM "{schema}".rotation_probe')).scalar() == 2
    finally:
        if old_engine: old_engine.dispose()
        if new_engine: new_engine.dispose()
        if migration_engine: migration_engine.dispose()
        with admin.begin() as conn:
            cursor = conn.connection.driver_connection.cursor()
            cursor.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))
            for role in (new, old, migrator, owner):
                cursor.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))
            cursor.close()
        admin.dispose()
