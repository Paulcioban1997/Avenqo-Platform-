"""Test Alembic Migration 0084 on an isolated database copy (SQLite and PostgreSQL).

Verifies:
- Linear migration head integrity (only 1 head: 0084_commerce_demo_isolation).
- Clean upgrade from 0083 to 0084.
- Addition of is_demo column to commerce_connections and normalized_commerce_records.
- Safe audit identification of legacy demo stores and demo products (is_demo=True).
- Strict non-regression of legitimate stores (is_demo=False).
- Reversibility via downgrade back to 0083.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory


@pytest.fixture
def isolated_db_url(monkeypatch):
    """Create an isolated temporary SQLite database for migration rehearsal."""
    pg_url = os.environ.get("AVENQO_TEST_POSTGRES_URL")
    if pg_url:
        yield pg_url
        return

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    url = f"sqlite:///{Path(db_path).as_posix()}"
    yield url

    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except OSError:
            pass


def test_alembic_0084_linear_head():
    """Verify Alembic history remains strictly linear with exactly one head."""
    alembic_cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(alembic_cfg)
    heads = script.get_heads()
    assert len(heads) == 1, f"Expected 1 linear Alembic head, got {heads}"
    assert heads[0] == "0084_commerce_demo_isolation"
    rev = script.get_revision("0084_commerce_demo_isolation")
    assert rev.down_revision == "0083_company_display_currency"


def test_alembic_0084_upgrade_downgrade_and_legacy_audit(isolated_db_url, monkeypatch):
    """Rehearse migration 0084 on a seeded pre-migration database."""
    project_root = Path(__file__).resolve().parents[2]
    alembic_ini_path = project_root / "alembic.ini"
    alembic_cfg = Config(str(alembic_ini_path))
    alembic_cfg.set_main_option("sqlalchemy.url", isolated_db_url)
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", isolated_db_url)

    engine = sa.create_engine(isolated_db_url)

    # 1. Upgrade to 0083 (pre-migration state)
    command.upgrade(alembic_cfg, "0083_company_display_currency")

    # Verify tables exist and do not have is_demo yet
    inspector = sa.inspect(engine)
    assert inspector.has_table("commerce_connections")
    assert inspector.has_table("normalized_commerce_records")
    cols_conn_pre = {c["name"] for c in inspector.get_columns("commerce_connections")}
    cols_rec_pre = {c["name"] for c in inspector.get_columns("normalized_commerce_records")}
    assert "is_demo" not in cols_conn_pre
    assert "is_demo" not in cols_rec_pre

    # 2. Seed data before migration: 1 company, 1 legacy demo store, 1 real store, products for both
    company_id = uuid4().hex if "sqlite" in isolated_db_url else uuid4()
    real_conn_id = uuid4().hex if "sqlite" in isolated_db_url else uuid4()
    demo_conn_id = uuid4().hex if "sqlite" in isolated_db_url else uuid4()
    real_prod_id = uuid4().hex if "sqlite" in isolated_db_url else uuid4()
    demo_prod_id = uuid4().hex if "sqlite" in isolated_db_url else uuid4()

    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO companies (id, name, slug, email, country, timezone, industry, subscription_plan, currency_code, status) "
                "VALUES (:id, 'Test Company', 'test-co', 'test@example.com', 'CA', 'America/Toronto', 'Retail', 'professional', 'CAD', 'active')"
            ),
            {"id": company_id},
        )
        # Real store
        conn.execute(
            sa.text(
                "INSERT INTO commerce_connections (id, company_id, provider, external_account_id, display_name, status, granted_scopes, capabilities, sync_cursor, dataset_ids, records_processed, records_created, records_updated, records_failed) "
                "VALUES (:id, :cid, 'woocommerce', 'https://real-store.com', 'Ma Vraie Boutique', 'READY', '[]', '[]', '{}', '{}', 0, 0, 0, 0)"
            ),
            {"id": real_conn_id, "cid": company_id},
        )
        # Legacy synthetic demo store (created before is_demo column existed)
        conn.execute(
            sa.text(
                "INSERT INTO commerce_connections (id, company_id, provider, external_account_id, display_name, status, granted_scopes, capabilities, sync_cursor, dataset_ids, records_processed, records_created, records_updated, records_failed) "
                "VALUES (:id, :cid, 'sandbox_demo', 'sandbox-demo-1234', 'Boutique Démo Sandbox (données fictives)', 'CONNECTED', '[]', '[]', '{}', '{}', 0, 0, 0, 0)"
            ),
            {"id": demo_conn_id, "cid": company_id},
        )
        # Product from real store
        conn.execute(
            sa.text(
                "INSERT INTO normalized_commerce_records (id, company_id, connection_id, provider, entity_type, source_record_id, normalized_data, deleted) "
                "VALUES (:id, :cid, :conn_id, 'woocommerce', 'product', 'real_prod_1', '{\"name\": \"Vrai Casque\", \"unit_price\": 100.0}', 0)"
            ),
            {"id": real_prod_id, "cid": company_id, "conn_id": real_conn_id},
        )
        # Product from legacy demo store
        conn.execute(
            sa.text(
                "INSERT INTO normalized_commerce_records (id, company_id, connection_id, provider, entity_type, source_record_id, normalized_data, deleted) "
                "VALUES (:id, :cid, :conn_id, 'sandbox_demo', 'product', 'demo_prod_1', '{\"name\": \"Planche Démo Fictive\", \"unit_price\": 500.0}', 0)"
            ),
            {"id": demo_prod_id, "cid": company_id, "conn_id": demo_conn_id},
        )

    # 3. Upgrade to 0084
    command.upgrade(alembic_cfg, "0084_commerce_demo_isolation")

    inspector_post = sa.inspect(engine)
    cols_conn_post = {c["name"] for c in inspector_post.get_columns("commerce_connections")}
    cols_rec_post = {c["name"] for c in inspector_post.get_columns("normalized_commerce_records")}
    assert "is_demo" in cols_conn_post
    assert "is_demo" in cols_rec_post

    # Verify audit values: legacy demo store is flagged is_demo=True, real store remains is_demo=False
    with engine.connect() as conn:
        real_store_demo = conn.scalar(
            sa.text("SELECT is_demo FROM commerce_connections WHERE id = :id"),
            {"id": real_conn_id},
        )
        demo_store_demo = conn.scalar(
            sa.text("SELECT is_demo FROM commerce_connections WHERE id = :id"),
            {"id": demo_conn_id},
        )
        assert bool(real_store_demo) is False, "Real store must remain is_demo=False"
        assert bool(demo_store_demo) is True, "Legacy demo store must be audited to is_demo=True"

        real_rec_demo = conn.scalar(
            sa.text("SELECT is_demo FROM normalized_commerce_records WHERE id = :id"),
            {"id": real_prod_id},
        )
        demo_rec_demo = conn.scalar(
            sa.text("SELECT is_demo FROM normalized_commerce_records WHERE id = :id"),
            {"id": demo_prod_id},
        )
        assert bool(real_rec_demo) is False, "Real product must remain is_demo=False"
        assert bool(demo_rec_demo) is True, "Legacy demo product must be audited to is_demo=True"

    # 4. Reversibility check: downgrade back to 0083
    command.downgrade(alembic_cfg, "0083_company_display_currency")
    inspector_down = sa.inspect(engine)
    cols_conn_down = {c["name"] for c in inspector_down.get_columns("commerce_connections")}
    cols_rec_down = {c["name"] for c in inspector_down.get_columns("normalized_commerce_records")}
    assert "is_demo" not in cols_conn_down
    assert "is_demo" not in cols_rec_down

    engine.dispose()
