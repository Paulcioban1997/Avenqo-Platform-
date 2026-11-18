"""Test Alembic Migration 0085 on an isolated database copy (SQLite and PostgreSQL).

Verifies:
- Linear migration head integrity (only 1 head: 0085_reconcile_legacy_demo_stores).
- Clean upgrade from 0084 to 0085.
- Detection and conversion of legacy demo stores created with the historical signature:
  * store_url = https://{provider}-store.avenqo.test
  * store_name = Boutique {provider} Sandbox
  * source_record_id = {provider}-prod-101, -102, -103, -104
  * fake last_successful_sync cleared to NULL
  * is_demo set to True
- Strict non-regression of legitimate stores (e.g. real-store.myshopify.com) which remain is_demo=False and keep their timestamps.
- Multi-tenant isolation during migration.
- Reversibility via downgrade.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
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


def test_alembic_0085_linear_head():
    """Verify Alembic history remains strictly linear with exactly one head."""
    alembic_cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(alembic_cfg)
    heads = script.get_heads()
    assert len(heads) == 1, f"Expected 1 linear Alembic head, got {heads}"
    assert heads[0] == "0085_reconcile_legacy_demo_stores"
    rev = script.get_revision("0085_reconcile_legacy_demo_stores")
    assert rev.down_revision == "0084_commerce_demo_isolation"


def test_alembic_0085_reconciliation_and_real_store_protection(isolated_db_url, monkeypatch):
    """Rehearse migration 0085 on a database with legacy demo stores and real customer stores."""
    project_root = Path(__file__).resolve().parents[2]
    alembic_ini_path = project_root / "alembic.ini"
    alembic_cfg = Config(str(alembic_ini_path))
    alembic_cfg.set_main_option("sqlalchemy.url", isolated_db_url)
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", isolated_db_url)

    engine = sa.create_engine(isolated_db_url)

    # 1. Upgrade to 0084 (state before 0085)
    command.upgrade(alembic_cfg, "0084_commerce_demo_isolation")

    # 2. Seed data in 0084:
    # Company A (Customer with real store)
    # Company B (Customer with legacy demo store missed by 0084)
    company_a_id = uuid4().hex if "sqlite" in isolated_db_url else uuid4()
    company_b_id = uuid4().hex if "sqlite" in isolated_db_url else uuid4()
    real_conn_id = uuid4().hex if "sqlite" in isolated_db_url else uuid4()
    legacy_demo_conn_id = uuid4().hex if "sqlite" in isolated_db_url else uuid4()
    real_prod_id = uuid4().hex if "sqlite" in isolated_db_url else uuid4()
    legacy_demo_prod1_id = uuid4().hex if "sqlite" in isolated_db_url else uuid4()
    legacy_demo_prod2_id = uuid4().hex if "sqlite" in isolated_db_url else uuid4()

    fake_now = datetime.now(timezone.utc)

    with engine.begin() as conn:
        # Seed companies
        conn.execute(
            sa.text(
                "INSERT INTO companies (id, name, slug, email, country, timezone, industry, subscription_plan, currency_code, status) "
                "VALUES (:id, 'Real Customer Co', 'real-co', 'customer@example.com', 'CA', 'America/Toronto', 'Retail', 'professional', 'CAD', 'active')"
            ),
            {"id": company_a_id},
        )
        conn.execute(
            sa.text(
                "INSERT INTO companies (id, name, slug, email, country, timezone, industry, subscription_plan, currency_code, status) "
                "VALUES (:id, 'Demo User Co', 'demo-co', 'demo@example.com', 'CA', 'America/Toronto', 'Retail', 'base', 'CAD', 'active')"
            ),
            {"id": company_b_id},
        )

        # Real store in Company A
        conn.execute(
            sa.text(
                "INSERT INTO commerce_connections ("
                "  id, company_id, provider, external_account_id, display_name, status, "
                "  granted_scopes, capabilities, sync_cursor, dataset_ids, records_processed, "
                "  records_created, records_updated, records_failed, last_successful_sync, is_demo"
                ") VALUES ("
                "  :id, :cid, 'shopify', 'https://boutique-reelle.myshopify.com', 'Boutique Réelle Client', 'READY', "
                "  '[]', '[]', '{}', '{}', 10, 10, 0, 0, :sync_at, false"
                ")"
            ),
            {"id": real_conn_id, "cid": company_a_id, "sync_at": fake_now},
        )
        conn.execute(
            sa.text(
                "INSERT INTO normalized_commerce_records ("
                "  id, company_id, connection_id, provider, entity_type, source_record_id, "
                "  normalized_data, deleted, is_demo"
                ") VALUES ("
                "  :id, :cid, :conn_id, 'shopify', 'product', 'real-prod-999', "
                "  '{\"title\": \"Vrai Produit Commercial\"}', false, false"
                ")"
            ),
            {"id": real_prod_id, "cid": company_a_id, "conn_id": real_conn_id},
        )

        # Legacy Demo Store in Company B (created before 0084, with signature missed by 0084)
        conn.execute(
            sa.text(
                "INSERT INTO commerce_connections ("
                "  id, company_id, provider, external_account_id, display_name, status, "
                "  granted_scopes, capabilities, sync_cursor, dataset_ids, records_processed, "
                "  records_created, records_updated, records_failed, last_successful_sync, is_demo"
                ") VALUES ("
                "  :id, :cid, 'shopify', 'https://shopify-store.avenqo.test', 'Boutique Shopify Sandbox', 'CONNECTED', "
                "  '[]', '[]', '{}', '{}', 4, 4, 0, 0, :sync_at, false"
                ")"
            ),
            {"id": legacy_demo_conn_id, "cid": company_b_id, "sync_at": fake_now},
        )
        conn.execute(
            sa.text(
                "INSERT INTO normalized_commerce_records ("
                "  id, company_id, connection_id, provider, entity_type, source_record_id, "
                "  normalized_data, deleted, is_demo"
                ") VALUES ("
                "  :id, :cid, :conn_id, 'shopify', 'product', 'shopify-prod-101', "
                "  '{\"title\": \"Planche All-Mountain Shopify Pro\"}', false, false"
                ")"
            ),
            {"id": legacy_demo_prod1_id, "cid": company_b_id, "conn_id": legacy_demo_conn_id},
        )
        conn.execute(
            sa.text(
                "INSERT INTO normalized_commerce_records ("
                "  id, company_id, connection_id, provider, entity_type, source_record_id, "
                "  normalized_data, deleted, is_demo"
                ") VALUES ("
                "  :id, :cid, :conn_id, 'shopify', 'product', 'shopify-prod-102', "
                "  '{\"title\": \"Fixations Freeride Shopify Elite\"}', false, false"
                ")"
            ),
            {"id": legacy_demo_prod2_id, "cid": company_b_id, "conn_id": legacy_demo_conn_id},
        )

    # 3. Apply migration 0085
    command.upgrade(alembic_cfg, "0085_reconcile_legacy_demo_stores")

    # 4. Verify results
    with engine.connect() as conn:
        # Verify real store is completely untouched
        real_res = conn.execute(
            sa.text("SELECT is_demo, last_successful_sync FROM commerce_connections WHERE id = :id"),
            {"id": real_conn_id},
        ).fetchone()
        assert real_res is not None
        assert bool(real_res[0]) is False, "Real customer store must remain is_demo=False"
        assert real_res[1] is not None, "Real store's last_successful_sync must not be cleared"

        real_rec = conn.execute(
            sa.text("SELECT is_demo FROM normalized_commerce_records WHERE id = :id"),
            {"id": real_prod_id},
        ).fetchone()
        assert real_rec is not None
        assert bool(real_rec[0]) is False, "Real customer product must remain is_demo=False"

        # Verify legacy demo store is correctly reconciled
        demo_res = conn.execute(
            sa.text("SELECT is_demo, last_successful_sync, sync_completed_at FROM commerce_connections WHERE id = :id"),
            {"id": legacy_demo_conn_id},
        ).fetchone()
        assert demo_res is not None
        assert bool(demo_res[0]) is True, "Legacy demo store must be flagged is_demo=True"
        assert demo_res[1] is None, "Fake last_successful_sync must be cleared to NULL"
        assert demo_res[2] is None, "Fake sync_completed_at must be cleared to NULL"

        # Verify legacy demo products are flagged is_demo=True
        demo_rec1 = conn.execute(
            sa.text("SELECT is_demo FROM normalized_commerce_records WHERE id = :id"),
            {"id": legacy_demo_prod1_id},
        ).fetchone()
        assert demo_rec1 is not None
        assert bool(demo_rec1[0]) is True, "Legacy demo product 101 must be flagged is_demo=True"

        demo_rec2 = conn.execute(
            sa.text("SELECT is_demo FROM normalized_commerce_records WHERE id = :id"),
            {"id": legacy_demo_prod2_id},
        ).fetchone()
        assert demo_rec2 is not None
        assert bool(demo_rec2[0]) is True, "Legacy demo product 102 must be flagged is_demo=True"

    # 5. Verify downgrade works cleanly
    command.downgrade(alembic_cfg, "0084_commerce_demo_isolation")
