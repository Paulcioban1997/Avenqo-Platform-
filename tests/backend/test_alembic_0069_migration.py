"""Test Alembic Migration 0069 on an isolated database copy.

Verifies:
- Clean upgrade from 0068 to 0069.
- Preservation of existing CRM services data.
- Unapproved demo services (category == 'clinic') have is_approved_by_owner=False, is_published=False.
- Standard services (category != 'clinic' or None) have is_approved_by_owner=True, is_published=True.
- Successful downgrade from 0069 back to 0068.
- Successful re-upgrade (idempotency & re-execution).
"""

import os
import tempfile
from pathlib import Path
from uuid import uuid4
import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic import command


@pytest.fixture
def isolated_db_url():
    """Create an isolated temporary SQLite database for migration rehearsal."""
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


def test_migration_0069_lifecycle_and_data_preservation(isolated_db_url):
    project_root = Path(__file__).resolve().parents[2]
    alembic_ini_path = project_root / "alembic.ini"
    alembic_cfg = Config(str(alembic_ini_path))
    alembic_cfg.set_main_option("sqlalchemy.url", isolated_db_url)
    os.environ["ALEMBIC_DATABASE_URL"] = isolated_db_url

    engine = sa.create_engine(isolated_db_url)

    # 1. Migrate up to 0068 (pre-migration state)
    command.upgrade(alembic_cfg, "0068_resolve_voice_phone_number_tenant")

    # Verify table crm_services exists and does NOT have the 0069 columns yet
    inspector = sa.inspect(engine)
    assert inspector.has_table("crm_services")
    cols_0068 = {c["name"] for c in inspector.get_columns("crm_services")}
    assert "is_approved_by_owner" not in cols_0068
    assert "is_published" not in cols_0068

    # 2. Seed pre-existing CRM services to test preservation and backfill rules
    company_id = uuid4()
    with engine.begin() as conn:
        # Create company first for foreign key
        conn.execute(
            sa.text(
                "INSERT INTO companies (id, name, slug, email, billing_email, timezone, industry, country, subscription_plan, status, created_at, updated_at) "
                "VALUES (:id, :name, :slug, :email, :bemail, :tz, :ind, :country, :plan, :st, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {
                "id": company_id.hex if "sqlite" in isolated_db_url else company_id,
                "name": "Produits_Ero",
                "slug": "produits-ero",
                "email": "test@produitsero.ca",
                "bemail": "billing@produitsero.ca",
                "tz": "America/Toronto",
                "ind": "sports_retail",
                "country": "CA",
                "plan": "growth",
                "st": "ACTIVE",
            },
        )

        # Service 1: Standard real service (Ski tuning)
        svc_standard_id = uuid4()
        conn.execute(
            sa.text(
                "INSERT INTO crm_services (id, company_id, name, category, price, duration_minutes, is_active, created_at, updated_at) "
                "VALUES (:id, :cid, :name, :cat, :price, :dur, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {
                "id": svc_standard_id.hex if "sqlite" in isolated_db_url else svc_standard_id,
                "cid": company_id.hex if "sqlite" in isolated_db_url else company_id,
                "name": "Affûtage & Fartage",
                "cat": "workshop",
                "price": 45.0,
                "dur": 45,
            },
        )

        # Service 2: Unapproved demo clinic service
        svc_demo_id = uuid4()
        conn.execute(
            sa.text(
                "INSERT INTO crm_services (id, company_id, name, category, price, duration_minutes, is_active, created_at, updated_at) "
                "VALUES (:id, :cid, :name, :cat, :price, :dur, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {
                "id": svc_demo_id.hex if "sqlite" in isolated_db_url else svc_demo_id,
                "cid": company_id.hex if "sqlite" in isolated_db_url else company_id,
                "name": "Consultation médicale démo",
                "cat": "clinic",
                "price": 120.0,
                "dur": 30,
            },
        )

    # 3. Execute Migration 0069 Upgrade
    command.upgrade(alembic_cfg, "0069_crm_service_approval_columns")

    # Verify schema after 0069
    inspector = sa.inspect(engine)
    cols_0069 = {c["name"] for c in inspector.get_columns("crm_services")}
    assert "is_approved_by_owner" in cols_0069
    assert "is_published" in cols_0069

    # Verify data backfill and security preservation:
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text("SELECT id, name, category, is_approved_by_owner, is_published FROM crm_services")
        ).fetchall()
        assert len(rows) == 2

        by_cat = {r[2]: r for r in rows}
        standard_row = by_cat["workshop"]
        demo_row = by_cat["clinic"]

        # Standard service: preserved, automatically approved & published
        assert bool(standard_row[3]) is True, "Standard non-clinic service must be approved"
        assert bool(standard_row[4]) is True, "Standard non-clinic service must be published"

        # Demo clinic service: preserved, but approval & publishing are FALSE!
        assert bool(demo_row[3]) is False, "Historical demo clinic service must NOT be approved"
        assert bool(demo_row[4]) is False, "Historical demo clinic service must NOT be published"

    # 4. Test Downgrade (0069 -> 0068)
    command.downgrade(alembic_cfg, "0068_resolve_voice_phone_number_tenant")

    inspector = sa.inspect(engine)
    cols_downgraded = {c["name"] for c in inspector.get_columns("crm_services")}
    assert "is_approved_by_owner" not in cols_downgraded
    assert "is_published" not in cols_downgraded

    # Verify data is still intact after downgrade!
    with engine.connect() as conn:
        count = conn.execute(sa.text("SELECT count(*) FROM crm_services")).scalar()
        assert count == 2, "Data must be preserved across downgrade"

    # 5. Test Re-upgrade (idempotency & re-execution)
    command.upgrade(alembic_cfg, "0069_crm_service_approval_columns")

    inspector = sa.inspect(engine)
    cols_reupgraded = {c["name"] for c in inspector.get_columns("crm_services")}
    assert "is_approved_by_owner" in cols_reupgraded
    assert "is_published" in cols_reupgraded
