"""Prepare synthetic Voice tenants in a supplied test session; no network calls.

Caller owns the transaction. No standalone database connection, migration,
subscription payment, phone purchase, routing change or deployment is performed.
"""
import secrets
from uuid import uuid4
from sqlalchemy.orm import Session
from backend.app.core.security import hash_password
from backend.app.models import Company, User, BillingAccount, CompanyMembership, UserRole, VoiceBusinessConfig
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from backend.app.services.tenant_locale_service import upsert_profile
from backend.app.services.voice_module_permission_service import VoiceModulePermissionService
from shared.ai_engine.contracts import TenantContext

SCENARIOS = (
    ("garage-montreal", "Garage Montreal QA", "CA", "America/Montreal", "fr", "crm", ("read_availability", "list_slots", "create_appointment")),
    ("ecommerce-english", "Ecommerce QA", "CA", "America/Toronto", "en", "retail", ("read_products", "read_inventory")),
    ("empresa-espanola", "Empresa QA", "ES", "Europe/Madrid", "es", "crm", ("read_availability",)),
)


def prepare_scenarios(db: Session, *, environment: str) -> dict:
    if environment not in {"sandbox", "test"}:
        raise ValueError("Synthetic scenarios require sandbox or test")
    result = {}
    run_id = uuid4().hex[:12]
    for key, name, country, zone, locale, module, actions in SCENARIOS:
        company = Company(name=name, slug=f"voice-qa-{key}-{run_id}", email=f"{key}-{run_id}@example.com", country=country, currency_code="EUR" if country=="ES" else "CAD", timezone=zone, industry="Synthetic Voice validation", subscription_plan="base", preferred_language=locale)
        company.business_hours = {"weekly": {day: [{"open": "09:00", "close": "17:00"}] for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")}}
        db.add(company); db.flush()
        owner = User(company_id=company.id, email=f"owner-{key}-{run_id}@example.com", first_name="Synthetic", last_name="QA", role=UserRole.OWNER, password_hash=hash_password(secrets.token_urlsafe(32)), is_active=True)
        db.add(owner); db.flush()
        db.add_all([BillingAccount(company_id=company.id, plan_code="base", status="trialing"), CompanyMembership(company_id=company.id, user_id=owner.id, role=UserRole.OWNER, is_active=True)])
        db.flush()
        tenant = TenantContext(company.id, owner.id)
        entitlements = ModuleEntitlementService(db)
        entitlements.activate_module(tenant, module)
        entitlements.activate_module(tenant, "voice", auto_init_voice=True)
        upsert_profile(db, company.id, primary_locale=locale, secondary_locales=[])
        grants = VoiceModulePermissionService(db)
        for action in actions:
            grants.grant(tenant, module, action, granted_by=owner.id)
        db.flush()
        result[key] = (company, owner)
    return result
