"""Test for Alembic migration 0070_employee_invitations_numeric_codes and backward compatibility."""

import os
from datetime import datetime, timezone, timedelta
from uuid import uuid4
import pytest
from sqlalchemy import create_engine, text, inspect
from alembic.config import Config
from alembic import command


def test_migration_0070_upgrade_and_downgrade(tmp_path, monkeypatch):
    """Test upgrade and downgrade of migration 0070 on a clean SQLite database."""
    db_path = tmp_path / "test_migration.db"
    db_url = f"sqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", db_url)

    alembic_cfg = Config(os.path.join(os.path.dirname(__file__), "..", "..", "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    alembic_cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "..", "alembic"))

    # Upgrade up to 0069
    command.upgrade(alembic_cfg, "0069_crm_service_approval_columns")

    engine = create_engine(db_url)
    with engine.connect() as conn:
        inspector = inspect(conn)
        cols_before = {c["name"] for c in inspector.get_columns("employee_invitations")}
        assert "code_hash" not in cols_before
        assert "code_salt" not in cols_before
        assert "failed_attempts" not in cols_before

        # Insert a legacy invitation (simulating pre-existing data in production/sandbox)
        cid = str(uuid4())
        uid = str(uuid4())
        inv_id = str(uuid4())
        now_iso = datetime.now(timezone.utc).isoformat()
        exp_iso = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        
        # Insert minimal company and user to satisfy any foreign keys if checked
        conn.execute(
            text("INSERT INTO companies (id, name, slug, email, country, timezone, industry, subscription_plan, status, created_at, updated_at) "
                 "VALUES (:id, 'TestCo', 'testco', 'test@co.com', 'Canada', 'America/Toronto', 'Retail', 'base', 'active', :now, :now)"),
            {"id": cid, "now": now_iso}
        )
        conn.execute(
            text("INSERT INTO users (id, email, password_hash, first_name, last_name, company_id, role, is_active, is_platform_admin, created_at, updated_at) "
                 "VALUES (:id, 'inviter@co.com', 'hash', 'Inv', 'Iter', :cid, 'owner', 1, 0, :now, :now)"),
            {"id": uid, "cid": cid, "now": now_iso}
        )
        conn.execute(
            text("INSERT INTO employee_invitations (id, company_id, invited_by_user_id, email, role, job_title, token_hash, expires_at, created_at, updated_at) "
                 "VALUES (:id, :cid, :uid, 'collab@co.com', 'user', 'Dev', 'legacy_token_hash_123', :exp, :now, :now)"),
            {"id": inv_id, "cid": cid, "uid": uid, "exp": exp_iso, "now": now_iso}
        )
        conn.commit()

    # Now run upgrade to 0070
    command.upgrade(alembic_cfg, "0070_employee_invitations_numeric_codes")

    with engine.connect() as conn:
        inspector = inspect(conn)
        cols_after = {c["name"] for c in inspector.get_columns("employee_invitations")}
        assert "code_hash" in cols_after
        assert "code_salt" in cols_after
        assert "failed_attempts" in cols_after

        # Verify the legacy row survived with NULL code_hash and default failed_attempts = 0
        row = conn.execute(
            text("SELECT id, email, token_hash, code_hash, code_salt, failed_attempts FROM employee_invitations WHERE id = :id"),
            {"id": inv_id}
        ).fetchone()
        assert row is not None
        assert row.token_hash == "legacy_token_hash_123"
        assert row.code_hash is None
        assert row.code_salt is None
        assert row.failed_attempts == 0

    # Test downgrade back to 0069
    command.downgrade(alembic_cfg, "0069_crm_service_approval_columns")

    with engine.connect() as conn:
        inspector = inspect(conn)
        cols_downgrade = {c["name"] for c in inspector.get_columns("employee_invitations")}
        assert "code_hash" not in cols_downgrade
        assert "code_salt" not in cols_downgrade
        assert "failed_attempts" not in cols_downgrade

        # Verify the legacy row is still intact
        row = conn.execute(
            text("SELECT id, email, token_hash FROM employee_invitations WHERE id = :id"),
            {"id": inv_id}
        ).fetchone()
        assert row is not None
        assert row.token_hash == "legacy_token_hash_123"
