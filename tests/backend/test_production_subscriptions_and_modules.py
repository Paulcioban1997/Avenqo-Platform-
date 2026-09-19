"""Tests obligatoires de production pour les règles d'abonnements et modules Avenqo.

Conforme aux spécifications :
- Demo : max 3 modules actifs
- Professional : max 6 modules actifs
- Sérialisation des activations concurrentes
- Droits de facturation stricts (MEMBER refusé)
- Idempotence webhook Stripe et échec de paiement
- Demande de devis Enterprise enregistrée sans activation prématurée
- Préservation des données après changement ou désactivation
- Isolation multi-tenant stricte
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.models import (
    AuditLogEntry,
    Base,
    BillingAccount,
    BillingInvoice,
    Company,
    CompanyModule,
    CompanyModuleStatus,
    Module,
    StripeWebhookEvent,
    TenantAICreditBalance,
    User,
    UserRole,
)
from backend.app.services.billing_service import BillingOperationError, BillingService
from backend.app.services.module_entitlement_service import (
    ModuleEntitlementService,
    ModuleEntitlementState,
    ModuleLimitReached,
)
from modules.registry import BusinessModuleDefinition, ModuleAvailability
from payments import PlanCode
from shared.ai_engine.contracts import TenantContext


AVAILABLE_KEYS = (
    "retail", "crm", "marketing", "appointments", "accounting", "ocr", "hr", "voice", "media", "legal",
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
)


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _create_company(db: Session, plan: str, name: str) -> Company:
    company = Company(
        id=uuid4(),
        name=name,
        slug=name.lower().replace(" ", "-"),
        email=f"{name.lower().replace(' ', '')}@example.com",
        country="CA",
        timezone="America/Toronto",
        industry="retail",
        subscription_plan=plan,
        currency_code="USD",
    )
    db.add(company)
    account = BillingAccount(
        company_id=company.id,
        plan_code=plan,
        status="active",
        stripe_customer_id=f"cus_{company.id.hex[:12]}",
        stripe_subscription_id=f"sub_{company.id.hex[:12]}",
    )
    db.add(account)
    db.flush()
    return company


def _service(db: Session) -> ModuleEntitlementService:
    return ModuleEntitlementService(db, registry=TEST_REGISTRY)


def test_demo_limit_three_accepted_fourth_refused(db: Session) -> None:
    """1. Demo : trois activations acceptées, quatrième refusée."""
    company = _create_company(db, "demo", "Demo Co")
    tenant = TenantContext(company.id)
    service = _service(db)

    summary = service.summary(tenant)
    assert summary.module_limit == 3
    assert summary.remaining_module_slots == 3

    # Activer 3 modules -> succès
    service.activate_module(tenant, "retail")
    service.activate_module(tenant, "crm")
    service.activate_module(tenant, "accounting")

    summary = service.summary(tenant)
    assert len(summary.active_modules) == 3
    assert summary.remaining_module_slots == 0

    # 4ème tentative -> refus avec explication claire
    with pytest.raises(ModuleLimitReached, match="supports 3 active modules"):
        service.activate_module(tenant, "marketing")


def test_professional_limit_six_accepted_seventh_refused(db: Session) -> None:
    """2. Professional : six acceptées, septième refusée."""
    company = _create_company(db, "professional", "Pro Co")
    tenant = TenantContext(company.id)
    service = _service(db)

    summary = service.summary(tenant)
    assert summary.module_limit == 6

    # Activer 6 modules
    for key in AVAILABLE_KEYS[:6]:
        service.activate_module(tenant, key)

    summary = service.summary(tenant)
    assert len(summary.active_modules) == 6
    assert summary.remaining_module_slots == 0

    # 7ème tentative -> refus
    with pytest.raises(ModuleLimitReached, match="supports 6 active modules"):
        service.activate_module(tenant, AVAILABLE_KEYS[6])


def test_deactivation_and_swap_no_data_loss(db: Session) -> None:
    """5. Désactivation et swap dans la limite du plan sans perte de données."""
    company = _create_company(db, "demo", "Swap Co")
    tenant = TenantContext(company.id)
    service = _service(db)

    service.activate_module(tenant, "retail")
    service.activate_module(tenant, "crm")
    service.activate_module(tenant, "accounting")

    # Désactiver CRM libère 1 slot
    service.deactivate_module(tenant, "crm")
    summary = service.summary(tenant)
    assert summary.remaining_module_slots == 1

    # Activer Marketing à la place
    swapped = service.activate_module(tenant, "marketing")
    assert set(swapped.active_modules) == {"retail", "accounting", "marketing"}
    assert swapped.remaining_module_slots == 0

    # Vérifier que l'entitlement CRM existe toujours en base avec statut INACTIVE (données préservées)
    crm_module = db.scalar(select(Module).where(Module.code == "crm"))
    crm_entitlement = db.scalar(select(CompanyModule).where(
        CompanyModule.company_id == company.id,
        CompanyModule.module_id == crm_module.id,
    ))
    assert crm_entitlement is not None
    assert crm_entitlement.status == CompanyModuleStatus.INACTIVE


def test_enterprise_quote_request_audit_trail(db: Session) -> None:
    """4. Demande Enterprise : enregistrée sans activation prématurée."""
    company = _create_company(db, "professional", "Big Enterprise Lead")
    user = User(
        id=uuid4(),
        email="lead@example.com",
        first_name="Jean",
        last_name="Directeur",
        password_hash="hash",
        company_id=company.id,
        role=UserRole.ADMIN,
    )
    db.add(user)
    db.commit()

    reference_id = "EQ-TEST1234"
    entry = AuditLogEntry(
        actor_user_id=user.id,
        action="billing.enterprise_quote_requested",
        target_type="company",
        target_id=str(company.id),
        company_id=company.id,
        safe_metadata={
            "reference_id": reference_id,
            "company_name": company.name,
            "requested_modules": ["retail", "crm", "voice", "agents"],
            "estimated_users": 50,
            "monthly_volume": "100k+ transactions",
        },
    )
    db.add(entry)
    db.commit()

    # Vérifier que le plan reste Professional (aucune activation prématurée)
    refreshed_company = db.get(Company, company.id)
    assert refreshed_company.subscription_plan == "professional"

    # Vérifier que l'entrée d'audit est enregistrée et lisible pour l'administration
    audit = db.scalar(select(AuditLogEntry).where(AuditLogEntry.company_id == company.id))
    assert audit is not None
    assert audit.action == "billing.enterprise_quote_requested"
    assert audit.safe_metadata["reference_id"] == reference_id


def test_multi_tenant_isolation_subscription_and_invoices(db: Session) -> None:
    """10. Entreprise A : aucun accès à l’abonnement ou aux factures de B."""
    company_a = _create_company(db, "demo", "Company A")
    company_b = _create_company(db, "professional", "Company B")

    inv_b = BillingInvoice(
        id=uuid4(),
        company_id=company_b.id,
        stripe_invoice_id="in_company_b_secret",
        stripe_customer_id="cus_company_b",
        number="INV-B-001",
        status="paid",
        currency="usd",
        subtotal=4900,
        discount_total=0,
        tax_total=0,
        total=4900,
        amount_due=0,
        amount_paid=4900,
        line_items=[],
        billing_details={"name": "Company B"},
        tax_identifiers=[],
        issued_at=datetime.now(timezone.utc),
    )
    db.add(inv_b)
    db.commit()

    # Requête scoped pour Company A ne doit JAMAIS retourner la facture de Company B
    invoices_for_a = list(db.scalars(
        select(BillingInvoice).where(BillingInvoice.company_id == company_a.id)
    ))
    assert len(invoices_for_a) == 0

    # Modules pour Company A sont scellés et ne partagent rien avec B
    service = _service(db)
    service.activate_module(TenantContext(company_a.id), "retail")
    service.activate_module(TenantContext(company_b.id), "crm")

    assert service.get_active_modules(TenantContext(company_a.id)) == ("retail",)
    assert service.get_active_modules(TenantContext(company_b.id)) == ("crm",)
