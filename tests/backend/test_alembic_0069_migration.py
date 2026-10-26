"""Test Alembic Migration 0069 on an isolated database copy (SQLite and PostgreSQL).

Verifies:
- Fail-closed migration behavior without category heuristics.
- Clean upgrade from 0068 to 0069.
- Preservation of verified active business services (services with historical confirmed appointments).
- Strict non-publication of unverified services, even when category != 'clinic'.
- Strict non-publication of unapproved demo services (category == 'clinic').
- Clean downgrade from 0069 back to 0068 without data loss.
- Successful re-upgrade (idempotency & re-execution).
- Zero environment variable bleed (uses pytest monkeypatch).
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


def test_migration_0069_fail_closed_lifecycle_and_historical_preservation(isolated_db_url, monkeypatch):
    project_root = Path(__file__).resolve().parents[2]
    alembic_ini_path = project_root / "alembic.ini"
    alembic_cfg = Config(str(alembic_ini_path))
    alembic_cfg.set_main_option("sqlalchemy.url", isolated_db_url)
    
    # Use monkeypatch so ALEMBIC_DATABASE_URL never persists outside this test
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", isolated_db_url)

    engine = sa.create_engine(isolated_db_url)

    # 1. Migrate up to 0068 (pre-migration state)
    command.upgrade(alembic_cfg, "0068_resolve_voice_phone_number_tenant")

    # Verify table crm_services exists and does NOT have the 0069 columns yet
    inspector = sa.inspect(engine)
    assert inspector.has_table("crm_services")
    assert inspector.has_table("crm_appointments")
    cols_0068 = {c["name"] for c in inspector.get_columns("crm_services")}
    assert "is_approved_by_owner" not in cols_0068
    assert "is_published" not in cols_0068

    # 2. Seed pre-existing CRM services and appointments to test fail-closed rules
    company_id = uuid4()
    client_id = uuid4()
    svc_active_verified_id = uuid4()
    svc_draft_nonclinic_id = uuid4()
    svc_demo_clinic_id = uuid4()
    appt_id = uuid4()

    cid_val = company_id.hex if "sqlite" in isolated_db_url else company_id
    cli_val = client_id.hex if "sqlite" in isolated_db_url else client_id
    svc1_val = svc_active_verified_id.hex if "sqlite" in isolated_db_url else svc_active_verified_id
    svc2_val = svc_draft_nonclinic_id.hex if "sqlite" in isolated_db_url else svc_draft_nonclinic_id
    svc3_val = svc_demo_clinic_id.hex if "sqlite" in isolated_db_url else svc_demo_clinic_id
    appt_val = appt_id.hex if "sqlite" in isolated_db_url else appt_id

    with engine.begin() as conn:
        # Create company
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
                "plan": "growth",
                "st": "ACTIVE",
            },
        )

        # Create client for foreign key in crm_appointments
        conn.execute(
            sa.text(
                "INSERT INTO crm_clients (id, company_id, first_name, last_name, email, industry_metadata, tags, created_at, updated_at) "
                "VALUES (:id, :cid, :fn, :ln, :email, '{}', '[]', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {
                "id": cli_val,
                "cid": cid_val,
                "fn": "Marc",
                "ln": "Tremblay",
                "email": "marc.tremblay@test.ca",
            },
        )

        # Service 1: Real active service (Affûtage ski) with confirmed historical booking
        conn.execute(
            sa.text(
                "INSERT INTO crm_services (id, company_id, name, category, price, duration_minutes, is_active, created_at, updated_at) "
                "VALUES (:id, :cid, :name, :cat, :price, :dur, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {
                "id": svc1_val,
                "cid": cid_val,
                "name": "Affûtage & Fartage Compétition",
                "cat": "workshop",
                "price": 45.0,
                "dur": 45,
            },
        )

        # Service 2: Non-clinic unverified service without appointment proof (category != 'clinic')
        conn.execute(
            sa.text(
                "INSERT INTO crm_services (id, company_id, name, category, price, duration_minutes, is_active, created_at, updated_at) "
                "VALUES (:id, :cid, :name, :cat, :price, :dur, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {
                "id": svc2_val,
                "cid": cid_val,
                "name": "Entretien Vélo Draft",
                "cat": "custom_workshop",
                "price": 85.0,
                "dur": 60,
            },
        )

        # Service 3: Demo clinic service without appointment proof
        conn.execute(
            sa.text(
                "INSERT INTO crm_services (id, company_id, name, category, price, duration_minutes, is_active, created_at, updated_at) "
                "VALUES (:id, :cid, :name, :cat, :price, :dur, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {
                "id": svc3_val,
                "cid": cid_val,
                "name": "Consultation médicale démo",
                "cat": "clinic",
                "price": 120.0,
                "dur": 30,
            },
        )

        # Insert confirmed appointment linked to Service 1 (verifiable historical proof of commercial activity)
        conn.execute(
            sa.text(
                "INSERT INTO crm_appointments (id, company_id, client_id, service_id, title, status, start_time, end_time, industry_data, created_at, updated_at) "
                "VALUES (:id, :cid, :clid, :sid, :title, :st, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {
                "id": appt_val,
                "cid": cid_val,
                "clid": cli_val,
                "sid": svc1_val,
                "title": "Réservation client confirmée",
                "st": "confirmed",
            },
        )

    # 3. Execute Migration 0069 Upgrade
    command.upgrade(alembic_cfg, "0069_crm_service_approval_columns")

    # Verify schema after 0069
    inspector = sa.inspect(engine)
    cols_0069 = {c["name"] for c in inspector.get_columns("crm_services")}
    assert "is_approved_by_owner" in cols_0069
    assert "is_published" in cols_0069

    # Verify indexes exist
    indexes_0069 = {idx["name"] for idx in inspector.get_indexes("crm_services")}
    assert "ix_crm_services_is_approved_by_owner" in indexes_0069
    assert "ix_crm_services_is_published" in indexes_0069

    # 4. Verify data backfill and fail-closed rules:
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text("SELECT id, name, category, is_approved_by_owner, is_published FROM crm_services")
        ).fetchall()
        assert len(rows) == 3

        by_cat = {r[2]: r for r in rows}
        active_verified_row = by_cat["workshop"]
        draft_nonclinic_row = by_cat["custom_workshop"]
        demo_clinic_row = by_cat["clinic"]

        # 1. Service 1: Even with historical confirmed appointment, NOT auto-approved! (P10.2 pure fail-closed)
        assert bool(active_verified_row[3]) is False, "Historical appointment does NOT constitute owner commercial consent"
        assert bool(active_verified_row[4]) is False, "Historical appointment must NOT auto-publish service"

        # 2. Service 2: Non-clinic category WITHOUT appointment proof -> STRICTLY FALSE (FAIL-CLOSED)
        assert bool(draft_nonclinic_row[3]) is False, "Unverified non-clinic service must NOT be auto-approved"
        assert bool(draft_nonclinic_row[4]) is False, "Unverified non-clinic service must NOT be auto-published"

        # 3. Service 3: Clinic category WITHOUT appointment proof -> STRICTLY FALSE
        assert bool(demo_clinic_row[3]) is False, "Unverified demo clinic service must NOT be auto-approved"
        assert bool(demo_clinic_row[4]) is False, "Unverified demo clinic service must NOT be auto-published"

        # 4. Verify historical appointments and services are preserved 100% without data loss
        appt_count = conn.execute(sa.text("SELECT count(*) FROM crm_appointments")).scalar()
        assert appt_count == 1, "Historical customer appointments must be preserved intact"
        svc_count = conn.execute(sa.text("SELECT count(*) FROM crm_services")).scalar()
        assert svc_count == 3, "Historical services must be preserved intact"

    # 5. Verify the Read-Only Inventory Script on this database
    from scripts.crm_migration_services_inventory import run_inventory
    inventory = run_inventory(isolated_db_url)
    assert inventory["status"] == "AUDIT_COMPLETE"
    assert inventory["total_services"] == 3
    assert inventory["services_with_historical_appointments"] == 1
    assert inventory["services_requiring_owner_review"] == 1
    assert inventory["companies"][0]["name"] == "Produits_Ero"
    # Verify Produits_Ero clinic demo service is explicitly unapproved
    clinic_svc = next(s for s in inventory["companies"][0]["services"] if s["category"] == "clinic")
    assert clinic_svc["is_approved_by_owner"] is False
    assert clinic_svc["is_published"] is False
    assert clinic_svc["status_flag"] == "UNPUBLISHED_INACTIVE_OR_DRAFT"

    # 6. Test Downgrade (0069 -> 0068)
    command.downgrade(alembic_cfg, "0068_resolve_voice_phone_number_tenant")

    inspector = sa.inspect(engine)
    cols_downgraded = {c["name"] for c in inspector.get_columns("crm_services")}
    assert "is_approved_by_owner" not in cols_downgraded
    assert "is_published" not in cols_downgraded

    # Verify data is still intact after downgrade!
    with engine.connect() as conn:
        count = conn.execute(sa.text("SELECT count(*) FROM crm_services")).scalar()
        assert count == 3, "All 3 services must be preserved across downgrade"
        appt_count = conn.execute(sa.text("SELECT count(*) FROM crm_appointments")).scalar()
        assert appt_count == 1, "Appointment must be preserved across downgrade"

    # 7. Test Re-upgrade (idempotency & re-execution)
    command.upgrade(alembic_cfg, "0069_crm_service_approval_columns")

    inspector = sa.inspect(engine)
    cols_reupgraded = {c["name"] for c in inspector.get_columns("crm_services")}
    assert "is_approved_by_owner" in cols_reupgraded
    assert "is_published" in cols_reupgraded

    with engine.connect() as conn:
        all_unapproved = conn.execute(
            sa.text("SELECT count(*) FROM crm_services WHERE is_approved_by_owner = true OR is_published = true")
        ).scalar()
        assert all_unapproved == 0, "All services must remain strictly fail-closed after re-upgrade"
