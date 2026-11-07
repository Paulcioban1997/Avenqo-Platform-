"""Test Alembic Migration 0074 on an isolated database (SQLite and PostgreSQL).

Verifies:
- Clean upgrade from 0073 to 0074.
- Verification that table secure_download_nonces and its indexes are created.
- Verification that nonces can be inserted and queried with unique constraints.
- Clean downgrade from 0074 back to 0073 without impacting other tables.
- Successful re-upgrade (idempotency and re-execution).
- Zero environment variable bleed (uses pytest monkeypatch).
"""

import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config


@pytest.fixture
def isolated_db_url(monkeypatch):
    """Create an isolated temporary SQLite database for migration rehearsal.

    If AVENQO_TEST_POSTGRES_URL is set, tests against that isolated PostgreSQL instance.
    """
    pg_url = os.environ.get("AVENQO_TEST_POSTGRES_URL")
    if pg_url:
        yield pg_url
        return

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    url = f"sqlite:///{Path(db_path).as_posix()}"
    yield url

    # Cleanup
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except OSError:
            pass


def test_migration_0074_upgrade_downgrade_and_idempotency(isolated_db_url, monkeypatch):
    project_root = Path(__file__).resolve().parents[2]
    alembic_ini_path = project_root / "alembic.ini"
    alembic_cfg = Config(str(alembic_ini_path))
    alembic_cfg.set_main_option("sqlalchemy.url", isolated_db_url)

    # Use monkeypatch so ALEMBIC_DATABASE_URL never persists outside this test
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", isolated_db_url)

    engine = sa.create_engine(isolated_db_url)

    # 1. Migrate up to 0073 (pre-migration state)
    command.upgrade(alembic_cfg, "0073_contract_signing_challenges")

    # Verify table secure_download_nonces does NOT exist yet
    inspector = sa.inspect(engine)
    assert not inspector.has_table("secure_download_nonces")

    # 2. Upgrade to 0074
    command.upgrade(alembic_cfg, "0074_secure_download_nonces")

    inspector = sa.inspect(engine)
    assert inspector.has_table("secure_download_nonces")

    # Inspect columns
    cols = {c["name"] for c in inspector.get_columns("secure_download_nonces")}
    expected_cols = {
        "id",
        "nonce",
        "company_id",
        "user_id",
        "doc_id",
        "doc_type",
        "expires_at",
        "redeemed_at",
    }
    assert expected_cols.issubset(cols)

    # Inspect indexes
    indexes = inspector.get_indexes("secure_download_nonces")
    index_names = {idx["name"] for idx in indexes}
    assert "ix_secure_download_nonces_nonce" in index_names
    assert "ix_secure_download_nonces_company_id" in index_names
    assert "ix_secure_download_nonces_user_id" in index_names
    assert "ix_secure_download_nonces_expires_at" in index_names

    # Check unique constraint on nonce index
    nonce_index = next(idx for idx in indexes if idx["name"] == "ix_secure_download_nonces_nonce")
    assert nonce_index.get("unique") is True or nonce_index.get("unique") == 1

    # 3. Seed test company, user, and insert nonce to verify integrity
    company_id = uuid4()
    user_id = uuid4()
    doc_id = uuid4()
    nonce_id = uuid4()
    test_nonce = "abc123nonce4567890abcdef1234567890abcdef1234567890abcdef1234567890"

    cid_val = company_id.hex if "sqlite" in isolated_db_url else company_id
    uid_val = user_id.hex if "sqlite" in isolated_db_url else user_id
    doc_val = doc_id.hex if "sqlite" in isolated_db_url else doc_id
    nid_val = nonce_id.hex if "sqlite" in isolated_db_url else nonce_id

    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=15)

    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO companies (id, name, slug, email, billing_email, timezone, industry, country, subscription_plan, status, created_at, updated_at) "
                "VALUES (:id, :name, :slug, :email, :bemail, :tz, :ind, :country, :plan, :st, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {
                "id": cid_val,
                "name": "Produits_Ero",
                "slug": f"produits-ero-{uuid4().hex[:6]}",
                "email": "test@produitsero.ca",
                "bemail": "billing@produitsero.ca",
                "tz": "America/Toronto",
                "ind": "sports_retail",
                "country": "CA",
                "plan": "professional",
                "st": "ACTIVE",
            },
        )
        conn.execute(
            sa.text(
                "INSERT INTO users (id, company_id, email, password_hash, first_name, last_name, role, is_active, is_platform_admin, created_at, updated_at) "
                "VALUES (:id, :cid, :email, 'hashed_pw', 'Paul', 'Mircea', 'OWNER', 1, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {
                "id": uid_val,
                "cid": cid_val,
                "email": f"owner-{uuid4().hex[:6]}@produitsero.ca",
            },
        )
        conn.execute(
            sa.text(
                "INSERT INTO secure_download_nonces (id, nonce, company_id, user_id, doc_id, doc_type, expires_at, redeemed_at) "
                "VALUES (:id, :nonce, :cid, :uid, :doc_id, :doc_type, :exp, :red)"
            ),
            {
                "id": nid_val,
                "nonce": test_nonce,
                "cid": cid_val,
                "uid": uid_val,
                "doc_id": doc_val,
                "doc_type": "contract",
                "exp": expires,
                "red": now,
            },
        )

        # Verify uniqueness violation on duplicate nonce
        with pytest.raises(Exception):
            conn.execute(
                sa.text(
                    "INSERT INTO secure_download_nonces (id, nonce, company_id, user_id, doc_id, doc_type, expires_at, redeemed_at) "
                    "VALUES (:id, :nonce, :cid, :uid, :doc_id, :doc_type, :exp, :red)"
                ),
                {
                    "id": (uuid4().hex if "sqlite" in isolated_db_url else uuid4()),
                    "nonce": test_nonce,
                    "cid": cid_val,
                    "uid": uid_val,
                    "doc_id": doc_val,
                    "doc_type": "contract",
                    "exp": expires,
                    "red": now,
                },
            )

    # 4. Downgrade cleanly to 0073
    command.downgrade(alembic_cfg, "0073_contract_signing_challenges")

    inspector = sa.inspect(engine)
    assert not inspector.has_table("secure_download_nonces")
    # Verify core tables remain untouched
    assert inspector.has_table("companies")
    assert inspector.has_table("users")
    assert inspector.has_table("company_contracts")

    # 5. Re-upgrade to 0074 (Idempotency and repeatable migration)
    command.upgrade(alembic_cfg, "0074_secure_download_nonces")

    inspector = sa.inspect(engine)
    assert inspector.has_table("secure_download_nonces")
