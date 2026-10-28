"""Rehearse the restricted 0048 -> head path in an isolated CI PostgreSQL database."""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from backend.app.services.postgres_app_role import MIGRATE_ROLE, OWNER_ROLE
from scripts.reassign_production_ownership import reassign_schema_objects


@pytest.mark.skipif(not os.getenv("AVENQO_TEST_POSTGRES_URL"), reason="Isolated PostgreSQL required")
def test_restored_schema_ownership_and_restricted_migration(monkeypatch):
    admin_url = make_url(os.environ["AVENQO_TEST_POSTGRES_URL"])
    assert admin_url.host in {"127.0.0.1", "localhost"}, "Never target a deployed database"
    name = "avenqo_ownership_rehearsal_" + uuid4().hex[:12]
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    target = admin_url.set(database=name)
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", target.render_as_string(hide_password=False))
    command.upgrade(config, "0048_billing_test_documents")

    engine = create_engine(target)
    try:
        with engine.connect() as connection:
            initial_tables = connection.execute(text(
                "SELECT count(*) FROM pg_tables WHERE schemaname='public'"
            )).scalar_one()
        results = reassign_schema_objects(engine, expected_database=name)
        assert initial_tables > 0
        assert results["tables_transferred"] == initial_tables
        with engine.begin() as connection:
            assert connection.execute(text(
                "SELECT pg_has_role('avenqo_migrate','avenqo_owner','USAGE')"
            )).scalar_one()
            assert connection.execute(text(
                "SELECT has_schema_privilege('avenqo_owner','public','CREATE')"
            )).scalar_one()
            assert not connection.execute(text(
                "SELECT pg_has_role('avenqo_app','avenqo_owner','MEMBER')"
            )).scalar_one()
            assert not connection.execute(text(
                "SELECT has_schema_privilege('avenqo_app','public','CREATE')"
            )).scalar_one()
            # This database is disposable CI data. Only its restricted migrator
            # receives a throwaway login for a direct-identity Alembic run.
            password = secrets.token_urlsafe(32)
            from psycopg2 import sql

            cursor = connection.connection.driver_connection.cursor()
            cursor.execute(sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}").format(
                sql.Identifier(MIGRATE_ROLE), sql.Literal(password)
            ))
            cursor.close()

        migrate_url = target.set(username=MIGRATE_ROLE, password=password)
        monkeypatch.setenv("ALEMBIC_DATABASE_URL", migrate_url.render_as_string(hide_password=False))
        command.upgrade(config, "head")
        with engine.connect() as connection:
            from alembic.script import ScriptDirectory

            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == ScriptDirectory.from_config(config).get_current_head()
            assert connection.execute(text(
                "SELECT tableowner FROM pg_tables WHERE schemaname='public' AND tablename='users'"
            )).scalar_one() == OWNER_ROLE
        with pytest.raises(DBAPIError):
            with engine.begin() as connection:
                connection.execute(text("SET LOCAL ROLE avenqo_app"))
                connection.execute(text(
                    "ALTER TABLE public.users ADD COLUMN forbidden_runtime_ddl integer"
                ))
    finally:
        engine.dispose()
        # The database and role login exist only for this isolated rehearsal.
        # Never leave a reusable migrator credential in the CI PostgreSQL host.
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
            connection.execute(text(f'ALTER ROLE {MIGRATE_ROLE} NOLOGIN PASSWORD NULL'))
        admin.dispose()
