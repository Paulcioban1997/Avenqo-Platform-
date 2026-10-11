"""Release rehearsal on a newly created, isolated PostgreSQL database only."""
import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url


@pytest.mark.skipif(not os.getenv("AVENQO_TEST_POSTGRES_URL"), reason="Isolated PostgreSQL required")
def test_postgres_0048_to_0050_preserves_data_and_accepts_long_revision_ids(monkeypatch):
    admin_url = make_url(os.environ["AVENQO_TEST_POSTGRES_URL"])
    assert admin_url.host in {"127.0.0.1", "localhost"}, "Never target a deployed database"
    name = "avenqo_release_rehearsal_" + uuid4().hex[:12]
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text('CREATE DATABASE "' + name + '"'))
    target = admin_url.set(database=name)
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", target.render_as_string(hide_password=False))
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    engine = create_engine(target)
    # Reproduce Alembic's default PostgreSQL version table before applying code.
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
    command.upgrade(config, "0048_billing_test_documents")
    with engine.begin() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0048_billing_test_documents"
        connection.execute(text("CREATE TABLE release_preservation_probe (id integer PRIMARY KEY, value text)"))
        connection.execute(text("INSERT INTO release_preservation_probe VALUES (1, 'test-only-preserve')"))
    command.upgrade(config, "0050_mfa_recovery_and_lockout")
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0050_mfa_recovery_and_lockout"
        assert connection.execute(text("SELECT value FROM release_preservation_probe")).scalar_one() == "test-only-preserve"
        columns = {item["name"] for item in inspect(connection).get_columns("users")}
        assert {"mfa_secret_encrypted", "mfa_recovery_hashes", "failed_login_count", "locked_until"} <= columns
        assert inspect(connection).get_columns("alembic_version")[0]["type"].length >= 64
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0052_company_locale_profile"
        assert connection.execute(text("SELECT value FROM release_preservation_probe")).scalar_one() == "test-only-preserve"
        assert inspect(connection).has_table("company_locale_profiles")
    engine.dispose()
    admin.dispose()
    # Keep the isolated rehearsal database for inspection; no active DB is deleted.
