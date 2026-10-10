"""Automated test suite for Universal Sector Profiles, Canonical Plans, and Multi-Tenant Quotas."""

from __future__ import annotations

from pathlib import Path
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.main import create_application
from backend.app.database import get_db
from backend.app.models import Base, BillingAccount, Company, CompanyMembership, User, UserRole
from backend.app.services.module_entitlement_service import (
    ModuleEntitlementService,
    ModuleLimitReached,
)
from modules.registry import BUSINESS_MODULES_BY_KEY
from payments.plans import PUBLIC_PLANS, PlanCode, get_plan
from shared.ai_engine.contracts import TenantContext
from shared.sector_profiles import SECTOR_PROFILES, SECTOR_PROFILES_BY_ID, get_sector_profile


@pytest.fixture
def db_session(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test_sectors_plans.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def test_sector_profiles_catalog_integrity():
    """Verify all 16 universal sectors exist with required metadata, recommended modules, and demo steps."""
    assert len(SECTOR_PROFILES) >= 16

    expected_sector_ids = {
        "retail_ecommerce",
        "garage_auto",
        "health_clinic",
        "restaurant_cafe",
        "hair_beauty",
        "real_estate",
        "construction",
        "transport_logistics",
        "education",
        "hospitality_tourism",
        "professional_services",
        "accounting_firms",
        "manufacturing_distribution",
        "service_companies",
        "associations_nonprofit",
        "other_custom",
    }
    actual_ids = {s.id for s in SECTOR_PROFILES}
    assert expected_sector_ids.issubset(actual_ids)

    official_module_keys = {"retail", "crm", "voice", "accounting", "marketing", "ocr"}

    for profile in SECTOR_PROFILES:
        assert len(profile.name_fr) > 0
        assert len(profile.name_en) > 0
        assert len(profile.description_fr) > 0
        assert len(profile.description_en) > 0
        assert len(profile.use_cases_fr) >= 2
        assert len(profile.use_cases_en) >= 2
        assert len(profile.demo_steps) >= 3
        # Recommended modules must be strictly among the official 6 business modules
        for mod in profile.recommended_modules:
            assert mod in official_module_keys, f"Invalid recommended module '{mod}' in sector {profile.id}"
        # Demo steps must have inputs and outputs
        for step in profile.demo_steps:
            assert step.step_number >= 1
            assert len(step.title_fr) > 0
            assert len(step.simulated_output) > 0


def test_canonical_plan_limits_and_pricing():
    """Verify Base has 2 modules / $29.99 CAD, Pro has 5 modules / $49.99 CAD, Enterprise is custom."""
    base_plan = get_plan(PlanCode.BASE)
    assert base_plan.max_selectable_modules == 2
    assert base_plan.exact_modules_count == 2
    assert base_plan.monthly_price_cad == 29.99
    assert base_plan.monthly_price_usd == 21.99
    assert base_plan.monthly_ai_credits == 6_500
    assert base_plan.max_users == 3
    assert base_plan.max_sites == 1
    assert base_plan.max_voice_agents == 1
    assert base_plan.max_concurrent_calls == 1

    pro_plan = get_plan(PlanCode.PROFESSIONAL)
    assert pro_plan.max_selectable_modules == 5
    assert pro_plan.exact_modules_count == 5
    assert pro_plan.monthly_price_cad == 49.99
    assert pro_plan.monthly_price_usd == 36.99
    assert pro_plan.monthly_ai_credits == 20_000
    assert pro_plan.max_users == 10
    assert pro_plan.max_sites == 3
    assert pro_plan.max_voice_agents == 3
    assert pro_plan.max_concurrent_calls == 2

    enterprise_plan = get_plan(PlanCode.ENTERPRISE)
    assert enterprise_plan.requires_sales_contact is True
    assert enterprise_plan.max_selectable_modules is None


def test_server_side_quota_enforcement_base_plan_limit(db_session: Session):
    """Verify that a Base plan company cannot activate a 3rd module without upgrading."""
    company = Company(
        id=uuid.uuid4(),
        name="Base Plan Co",
        slug=f"base-{uuid.uuid4().hex[:6]}",
        email="owner@base-test.ca",
        country="CA",
        timezone="America/Toronto",
        industry="retail_ecommerce",
        subscription_plan="base",
        currency_code="CAD",
    )
    user = User(
        id=uuid.uuid4(),
        company_id=company.id,
        email="owner@base-test.ca",
        first_name="Base",
        last_name="Owner",
        role=UserRole.OWNER,
        password_hash="test_hash",
        is_active=True,
    )
    account = BillingAccount(
        company_id=company.id,
        plan_code="base",
        status="active",
    )
    db_session.add_all([company, user, account])
    db_session.commit()

    tenant = TenantContext(company_id=company.id, user_id=user.id)
    service = ModuleEntitlementService(db_session)

    # 1st module: Success
    service.activate_module(tenant, "retail")
    # 2nd module: Success (Base quota = 2)
    service.activate_module(tenant, "crm")

    active = service.get_active_modules(tenant)
    assert len(active) == 2
    assert "retail" in active
    assert "crm" in active

    # 3rd module: Rejection (Base allows exactly 2 modules)
    with pytest.raises(ModuleLimitReached):
        service.activate_module(tenant, "accounting")


def test_sectors_api_endpoints(tmp_path: Path):
    """Verify GET /api/v1/sectors and GET /api/v1/sectors/{id} via TestClient."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'api_sectors.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    app = create_application()

    def override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db

    with TestClient(app) as client:
        # List all
        resp = client.get("/api/v1/sectors")
        assert resp.status_code == 200
        sectors = resp.json()
        assert len(sectors) >= 16
        first = sectors[0]
        assert "id" in first
        assert "name_fr" in first
        assert "recommended_modules" in first
        assert len(first["demo_steps"]) >= 3

        # Get specific sector
        resp_single = client.get("/api/v1/sectors/garage_auto")
        assert resp_single.status_code == 200
        data = resp_single.json()
        assert data["id"] == "garage_auto"
        assert "Garages" in data["name_fr"]

        # Not found
        resp_404 = client.get("/api/v1/sectors/nonexistent_sector_xyz")
        assert resp_404.status_code == 404
