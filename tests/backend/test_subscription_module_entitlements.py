from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.models import Base, Company, CompanyModule, Module, TenantAICreditBalance
from backend.app.services.module_entitlement_service import (
    ModuleEntitlementService,
    ModuleEntitlementState,
    ModuleLimitReached,
    ModuleUnavailable,
)
from modules.registry import BusinessModuleDefinition, ModuleAvailability
from shared.ai_engine.contracts import TenantContext


AVAILABLE_KEYS = (
    "retail", "crm", "marketing", "appointments", "accounting",
    "ocr", "hr", "voice", "media", "legal",
)
TEST_REGISTRY = tuple(
    BusinessModuleDefinition(
        key,
        key.title(),
        f"{key} module",
        ModuleAvailability.AVAILABLE,
        "test",
        premium=key in {"voice", "media"},
    )
    for key in AVAILABLE_KEYS
) + (
    BusinessModuleDefinition(
        "workflow",
        "Workflow",
        "Coming soon module",
        ModuleAvailability.COMING_SOON,
        "test",
    ),
)


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _company(db: Session, plan: str, slug: str) -> Company:
    company = Company(
        name=slug,
        slug=slug,
        email=f"{slug}@example.com",
        country="CA",
        timezone="America/Toronto",
        industry="retail",
        subscription_plan=plan,
    )
    db.add(company)
    db.flush()
    return company


def _service(db: Session) -> ModuleEntitlementService:
    return ModuleEntitlementService(db, registry=TEST_REGISTRY)


def test_demo_limit_swap_core_and_credit_independence(db: Session) -> None:
    company = _company(db, "demo", "demo-company")
    tenant = TenantContext(company.id)
    credits = TenantAICreditBalance(
        company_id=company.id,
        monthly_period="2026-09",
        monthly_used=4,
        purchased_balance=9,
    )
    db.add(credits)
    service = _service(db)

    initial = service.summary(tenant)
    assert initial.module_limit == 2
    assert initial.active_modules == ()
    assert initial.remaining_module_slots == 2
    assert "billing" not in {module.key for module in initial.modules}
    assert next(module for module in initial.modules if module.key == "retail").state == ModuleEntitlementState.AVAILABLE

    service.activate_module(tenant, "crm")
    service.activate_module(tenant, "marketing")
    with pytest.raises(ModuleLimitReached, match="supports 2 active modules"):
        service.activate_module(tenant, "accounting")

    service.deactivate_module(tenant, "crm")
    swapped = service.activate_module(tenant, "accounting")
    assert set(swapped.active_modules) == {"marketing", "accounting"}
    assert swapped.remaining_module_slots == 0
    assert credits.monthly_used == 4
    assert credits.purchased_balance == 9


def test_professional_limit_and_swap(db: Session) -> None:
    company = _company(db, "professional", "professional-company")
    tenant = TenantContext(company.id)
    service = _service(db)

    for key in AVAILABLE_KEYS[:8]:
        service.activate_module(tenant, key)
    assert service.summary(tenant).module_limit == 8
    with pytest.raises(ModuleLimitReached, match="supports 8 active modules"):
        service.activate_module(tenant, AVAILABLE_KEYS[8])

    service.deactivate_module(tenant, AVAILABLE_KEYS[0])
    summary = service.activate_module(tenant, AVAILABLE_KEYS[8])
    assert len(summary.active_modules) == 8
    assert AVAILABLE_KEYS[8] in summary.active_modules


def test_enterprise_all_available_and_coming_soon_never_consumes_slot(db: Session) -> None:
    company = _company(db, "enterprise", "enterprise-company")
    tenant = TenantContext(company.id)
    service = _service(db)

    for key in AVAILABLE_KEYS:
        service.activate_module(tenant, key)
    summary = service.summary(tenant)
    assert summary.module_limit is None
    assert summary.remaining_module_slots is None
    assert set(summary.active_modules) == set(AVAILABLE_KEYS)

    with pytest.raises(ModuleUnavailable):
        service.activate_module(tenant, "workflow")
    after = service.summary(tenant)
    assert len(after.active_modules) == len(AVAILABLE_KEYS)
    assert next(module for module in after.modules if module.key == "workflow").state == ModuleEntitlementState.COMING_SOON


def test_existing_rows_are_preserved_and_tenant_isolation_is_strict(db: Session) -> None:
    company_a = _company(db, "demo", "tenant-a")
    company_b = _company(db, "demo", "tenant-b")
    module = Module(name="Retail", code="retail")
    db.add(module)
    db.flush()
    existing = CompanyModule(
        id=uuid4(),
        company_id=company_a.id,
        module_id=module.id,
        activated_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    )
    db.add(existing)
    db.flush()
    service = _service(db)

    assert service.can_use_module(TenantContext(company_a.id), "retail") is True
    assert service.can_use_module(TenantContext(company_b.id), "retail") is False
    service.activate_module(TenantContext(company_b.id), "crm")
    service.deactivate_module(TenantContext(company_b.id), "retail")

    assert db.scalar(select(CompanyModule).where(CompanyModule.id == existing.id)) is existing
    assert service.can_use_module(TenantContext(company_a.id), "retail") is True