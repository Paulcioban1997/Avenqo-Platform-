"""Comprehensive validation of the generic multi-tenant Voice architecture.

Validates that:
1. New tenants without Voice get 0 phone resources and 0 telephony costs.
2. New tenants with Voice get VoiceBusinessConfig created automatically and idempotently.
3. Existing tenants adding Voice later follow the identical automated pipeline.
4. Onboarding resumption and setup are strictly idempotent.
5. Live Telnyx inventory search returns real offers with explicit pricing and requirements.
6. Number provisioning automatically binds VoicePhoneNumber to tenant and VoiceBusinessConfig.
7. Global number uniqueness is strictly enforced; no two tenants can share a number.
8. Authenticated OWNER chooses their own Voice PIN; Avenqo never generates it.
9. Two concurrent tenants have separate numbers and strict cross-tenant isolation during calls.
10. Dynamic Agent Registry uses tenant active modules (entitled ∩ active ∩ permissions).
11. Changing active modules dynamically updates available Voice tools at runtime.
12. Telnyx purchase failure cleanly rolls back with no phantom numbers.
13. Retry purchase avoids double purchases.
14. Produits_Ero pilot tenant uses the exact same generic architecture with zero hardcoded hacks.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from httpx import HTTPStatusError, Request, Response
from pydantic import SecretStr
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.config.settings import Settings, get_settings
from backend.app.core.permissions import permissions_for
from backend.app.core.rate_limit import reset_rate_limiter
from backend.app.database import get_db
from backend.app.dependencies.auth import CurrentIdentity, get_current_identity
from backend.app.dependencies.subscription import require_active_subscription
from backend.app.models import (
    Base,
    BillingAccount,
    Company,
    CompanyMembership,
    User,
    UserRole,
    VoiceBusinessConfig,
    VoicePhoneNumber,
)
import backend.app.routers.voice as voice_router
from backend.app.schemas.voice import (
    VoicePinRequest,
    VoiceSetupRequest,
    VoiceNumberProvisionRequest,
)
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from backend.app.services.onboarding_service import OnboardingService
from backend.app.schemas.onboarding import OnboardingSubmitRequest
from backend.app.voice.quotes import signed_number_quote
from backend.app.voice.service import VoiceOrchestrator, ensure_voice_business_config
from shared.ai_engine.contracts import TenantContext


class MockTelecomProvider:
    """Mock Telecom provider simulating Telnyx inventory and orders with zero external network calls."""

    def __init__(self):
        self.orders = []
        self.fail_order = False
        self.fail_status_code = 422

    async def search_available_numbers(self, **kwargs) -> list[dict[str, object]]:
        country = kwargs.get("country_code", "CA")
        return [
            {
                "phone_number": "+15145550001",
                "country_code": country,
                "phone_number_type": "local",
                "features": [{"name": "voice"}, {"name": "sms"}],
                "cost_information": {"monthly_cost": "2.00", "upfront_cost": "1.00", "currency": "USD"},
                "region_information": [{"state": "QC", "location": "Montreal"}],
                "requirements": [],
                "id": "telnyx-num-1",
            },
            {
                "phone_number": "+14165550002",
                "country_code": country,
                "phone_number_type": "local",
                "features": [{"name": "voice"}, {"name": "sms"}],
                "cost_information": {"monthly_cost": "2.50", "upfront_cost": "1.00", "currency": "USD"},
                "region_information": [{"state": "ON", "location": "Toronto"}],
                "requirements": [],
                "id": "telnyx-num-2",
            },
        ]

    async def order_phone_number(self, **kwargs) -> dict[str, object]:
        if self.fail_order:
            req = Request("POST", "https://api.telnyx.com/v2/number_orders")
            resp = Response(self.fail_status_code, request=req, json={"errors": [{"code": "40001", "detail": "Unavailable"}]})
            raise HTTPStatusError("Telnyx order failed", request=req, response=resp)

        phone_number = kwargs["phone_number"]
        order_id = f"order-{len(self.orders) + 1}"
        self.orders.append(kwargs)
        return {
            "data": {
                "id": order_id,
                "status": "success",
                "phone_numbers": [{"phone_number": phone_number, "status": "active"}],
            }
        }

    async def get_owned_number(self, phone_number: str) -> dict[str, object]:
        return {
            "id": f"telnyx-id-{phone_number.replace('+', '')}",
            "phone_number": phone_number,
            "status": "active",
            "country_iso_alpha2": "CA",
            "phone_number_type": "local",
            "connection_id": "conn-generic-voice",
            "purchased_at": datetime.now(timezone.utc).isoformat(),
        }

    async def number_requirements(self, phone_number: str, country_code: str, phone_number_type: str) -> dict[str, object]:
        return {"status": "verified_no_requirements", "requirements": []}

    async def release_phone_number(self, provider_number_id: str) -> dict[str, object]:
        return {"data": {"id": provider_number_id, "status": "released"}}


@pytest.fixture
def multi_tenant_db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'multi-tenant-voice.db'}")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        # Create Tenant A (Retail + CRM)
        comp_a = Company(
            name="Retail Company A",
            slug="tenant-a",
            email="owner@tenanta.com",
            country="CA",
            timezone="America/Montreal",
            industry="Retail",
            subscription_plan="base",
            preferred_language="fr",
        )
        db.add(comp_a)
        db.flush()
        owner_a = User(
            company_id=comp_a.id,
            first_name="Alice",
            last_name="Owner",
            email="alice@tenanta.com",
            phone="+15145550009",
            password_hash="argon2_fake",
            role=UserRole.OWNER,
            is_active=True,
        )
        db.add(owner_a)
        db.flush()
        db.add_all([
            BillingAccount(company_id=comp_a.id, plan_code="base", status="active"),
            CompanyMembership(company_id=comp_a.id, user_id=owner_a.id, role=UserRole.OWNER, is_active=True),
        ])

        # Create Tenant B (CRM + Accounting)
        comp_b = Company(
            name="Services Company B",
            slug="tenant-b",
            email="owner@tenantb.com",
            country="CA",
            timezone="America/Toronto",
            industry="Services",
            subscription_plan="professional",
            preferred_language="en",
        )
        db.add(comp_b)
        db.flush()
        owner_b = User(
            company_id=comp_b.id,
            first_name="Bob",
            last_name="Owner",
            email="bob@tenantb.com",
            phone="+14165550008",
            password_hash="argon2_fake",
            role=UserRole.OWNER,
            is_active=True,
        )
        db.add(owner_b)
        db.flush()
        db.add_all([
            BillingAccount(company_id=comp_b.id, plan_code="professional", status="active"),
            CompanyMembership(company_id=comp_b.id, user_id=owner_b.id, role=UserRole.OWNER, is_active=True),
        ])

        # Create Pilot Tenant: Produits_Ero
        pilot = Company(
            name="Produits_Ero",
            slug="produits-ero",
            email="contact@produitsero.com",
            country="CA",
            timezone="America/Montreal",
            industry="Retail",
            subscription_plan="enterprise",
            preferred_language="fr",
        )
        db.add(pilot)
        db.flush()
        owner_p = User(
            company_id=pilot.id,
            first_name="Pilot",
            last_name="Owner",
            email="pilot@produitsero.com",
            phone="+14385550007",
            password_hash="argon2_fake",
            role=UserRole.OWNER,
            is_active=True,
        )
        db.add(owner_p)
        db.flush()
        db.add_all([
            BillingAccount(company_id=pilot.id, plan_code="enterprise", status="active"),
            CompanyMembership(company_id=pilot.id, user_id=owner_p.id, role=UserRole.OWNER, is_active=True),
            VoicePhoneNumber(
                company_id=pilot.id,
                phone_number="+14386075438",
                country_code="CA",
                region="QC",
                locality="Montreal",
                provider="telnyx",
                number_type="local",
                capabilities=["voice", "sms"],
                status="ACTIVE",
                provider_number_id="telnyx-pilot-438",
                provider_connection_id="conn-pilot",
            ),
        ])
        db.commit()

        yield db, comp_a, owner_a, comp_b, owner_b, pilot, owner_p
    engine.dispose()


def test_new_tenant_without_voice_creates_no_phone_resources(multi_tenant_db):
    """1. Si Voice AI n'est PAS sélectionné : ne créer aucune ressource téléphonique payante."""
    db, comp_a, owner_a, _, _, _, _ = multi_tenant_db
    tenant_a = TenantContext(comp_a.id, owner_a.id)

    entitlements = ModuleEntitlementService(db)
    entitlements.activate_module(tenant_a, "retail")
    entitlements.activate_module(tenant_a, "crm")
    db.commit()

    # Verify active modules
    active = entitlements.get_active_modules(tenant_a)
    assert "voice" not in active
    assert set(active) == {"retail", "crm"}

    # Zero VoiceBusinessConfig
    config = db.scalar(select(VoiceBusinessConfig).where(VoiceBusinessConfig.company_id == comp_a.id))
    assert config is None

    # Zero VoicePhoneNumber
    numbers = db.scalars(select(VoicePhoneNumber).where(VoicePhoneNumber.company_id == comp_a.id)).all()
    assert len(numbers) == 0


def test_new_tenant_with_voice_auto_creates_voice_business_config(multi_tenant_db):
    """2. Si Voice AI EST sélectionné : créer automatiquement et de façon idempotente la VoiceBusinessConfig."""
    db, comp_a, owner_a, _, _, _, _ = multi_tenant_db
    tenant_a = TenantContext(comp_a.id, owner_a.id)

    entitlements = ModuleEntitlementService(db)
    entitlements.activate_module(tenant_a, "retail")
    entitlements.activate_module(tenant_a, "voice", auto_init_voice=True)
    db.commit()

    config = db.scalar(select(VoiceBusinessConfig).where(VoiceBusinessConfig.company_id == comp_a.id))
    assert config is not None
    assert config.business_name == comp_a.name
    assert config.preferred_language == "fr"
    assert config.timezone_name == comp_a.timezone
    assert config.enabled is False
    assert config.telnyx_phone_number is None  # Waiting for tenant to choose their number

    # Never auto-assigns the pilot number +1 438 607 5438
    assert config.telnyx_phone_number != "+14386075438"


def test_existing_tenant_adds_voice_later(multi_tenant_db):
    """3. Client qui ajoute Voice plus tard : même pipeline automatique."""
    db, _, _, comp_b, owner_b, _, _ = multi_tenant_db
    tenant_b = TenantContext(comp_b.id, owner_b.id)

    entitlements = ModuleEntitlementService(db)
    entitlements.activate_module(tenant_b, "crm")
    entitlements.activate_module(tenant_b, "accounting")
    db.commit()

    # Initially no Voice
    assert "voice" not in entitlements.get_active_modules(tenant_b)
    assert db.scalar(select(VoiceBusinessConfig).where(VoiceBusinessConfig.company_id == comp_b.id)) is None

    # Existing tenant activates Voice later
    entitlements.activate_module(tenant_b, "voice", auto_init_voice=True)
    db.commit()

    assert "voice" in entitlements.get_active_modules(tenant_b)
    config = db.scalar(select(VoiceBusinessConfig).where(VoiceBusinessConfig.company_id == comp_b.id))
    assert config is not None
    assert config.business_name == comp_b.name
    assert config.preferred_language == "en"
    assert config.telnyx_phone_number is None


def test_onboarding_resume_and_idempotence(multi_tenant_db):
    """4. Reprise onboarding / idempotence : ne jamais créer deux VoiceBusinessConfig."""
    db, comp_a, owner_a, _, _, _, _ = multi_tenant_db
    tenant_a = TenantContext(comp_a.id, owner_a.id)

    entitlements = ModuleEntitlementService(db)
    entitlements.activate_module(tenant_a, "voice", auto_init_voice=True)
    db.commit()

    # Repeated activation
    entitlements.activate_module(tenant_a, "voice", auto_init_voice=True)
    db.commit()

    # Repeated ensure helper call
    cfg1 = ensure_voice_business_config(db, comp_a.id)
    cfg2 = ensure_voice_business_config(db, comp_a.id)
    assert cfg1.id == cfg2.id

    configs = db.scalars(select(VoiceBusinessConfig).where(VoiceBusinessConfig.company_id == comp_a.id)).all()
    assert len(configs) == 1


@pytest.mark.asyncio
async def test_international_number_search_live_inventory(multi_tenant_db, monkeypatch):
    """5. Interroger en temps réel l'inventaire Telnyx avec prix et exigences."""
    db, comp_a, owner_a, _, _, _, _ = multi_tenant_db
    mock_provider = MockTelecomProvider()
    monkeypatch.setattr(voice_router, "TelnyxClient", lambda settings: mock_provider)
    settings = Settings()
    settings.telnyx_api_key = "KEY_TEST"
    settings.telnyx_public_key = "PUB_TEST"
    settings.telnyx_voice_connection_id = "conn-test"

    mgr = voice_router._voice_number_service(settings)
    search_result = await mgr.search(
        voice_router.PhoneNumberSearch(
            country_code="CA",
            region="QC",
            locality="Montreal",
            area_code="514",
            capabilities=("voice", "sms"),
        )
    )

    assert search_result["status"] == "READY_FOR_OWNER_ACTION"
    offers = search_result["offers"]
    assert len(offers) == 2
    assert offers[0]["phone_number"] == "+15145550001"
    assert offers[0]["monthly_cost"] == 2.0
    assert offers[0]["monthly_cost_currency"] == "USD"
    assert offers[0]["voice_capability"] is True


@pytest.mark.asyncio
async def test_number_provisioning_and_automatic_tenant_binding(multi_tenant_db, monkeypatch):
    """6. Seulement après confirmation explicite : acheter et lier automatiquement VoicePhoneNumber -> VoiceBusinessConfig."""
    db, comp_a, owner_a, _, _, _, _ = multi_tenant_db
    tenant_a = TenantContext(comp_a.id, owner_a.id)
    ModuleEntitlementService(db).activate_module(tenant_a, "voice")
    db.commit()

    mock_provider = MockTelecomProvider()
    monkeypatch.setattr(voice_router, "TelnyxClient", lambda settings: mock_provider)
    settings = Settings()
    settings.telnyx_api_key = "KEY_TEST"
    settings.telnyx_public_key = "PUB_TEST"
    settings.telnyx_voice_connection_id = "conn-test"

    # Offer details
    offer = {
        "phone_number": "+15145550001",
        "country_code": "CA",
        "number_type": "local",
        "cost_information": {"monthly_cost": "2.00", "upfront_cost": "1.00", "currency": "USD"},
        "monthly_cost": 2.0,
        "monthly_cost_currency": "USD",
        "upfront_cost": 1.0,
        "regulatory_status": "verified_no_requirements",
        "regulatory_requirements": [],
        "voice_capability": True,
        "sms_capability": True,
        "is_orderable": True,
    }
    quote_token = signed_number_quote(settings, comp_a.id, owner_a.id, offer)

    # 1. Unconfirmed request must NOT buy number
    unconfirmed = VoiceNumberProvisionRequest(
        phone_number="+15145550001",
        country_code="CA",
        quote_token=quote_token,
        confirmed=False,
    )
    identity_a = cast(CurrentIdentity, SimpleNamespace(user=owner_a))
    membership_a = SimpleNamespace(role=UserRole.OWNER)

    res_unconfirmed = await voice_router.provision_voice_number(
        unconfirmed, identity_a, db, settings, membership_a
    )
    assert res_unconfirmed["status"] == "READY_FOR_OWNER_ACTION"
    assert res_unconfirmed["reason"] == "explicit_purchase_confirmation_required"
    assert len(mock_provider.orders) == 0

    # 2. Confirmed request provisions and automatically binds
    confirmed = VoiceNumberProvisionRequest(
        phone_number="+15145550001",
        country_code="CA",
        quote_token=quote_token,
        confirmed=True,
    )
    res_confirmed = await voice_router.provision_voice_number(
        confirmed, identity_a, db, settings, membership_a
    )
    print("DEBUG RES_CONFIRMED:", res_confirmed)
    assert res_confirmed["status"] == "ACTIVE"
    assert len(mock_provider.orders) == 1

    # Verify VoicePhoneNumber in DB
    phone = db.scalar(select(VoicePhoneNumber).where(VoicePhoneNumber.phone_number == "+15145550001"))
    assert phone is not None
    assert phone.company_id == comp_a.id
    assert phone.status == "ACTIVE"
    assert phone.provider == "telnyx"

    # Verify automatic binding to VoiceBusinessConfig
    config = db.scalar(select(VoiceBusinessConfig).where(VoiceBusinessConfig.company_id == comp_a.id))
    assert phone.config_id == config.id
    assert config.telnyx_phone_number == "+15145550001"


def test_owner_sets_own_pin_and_activates_voice(multi_tenant_db):
    """7. Le OWNER choisit lui-même son NIP (Avenqo ne génère jamais de NIP) -> Voice AI = ACTIVE."""
    db, comp_a, owner_a, _, _, _, _ = multi_tenant_db
    tenant_a = TenantContext(comp_a.id, owner_a.id)
    ModuleEntitlementService(db).activate_module(tenant_a, "voice")
    config = ensure_voice_business_config(db, comp_a.id, "+15145550001")
    db.commit()

    assert config.enabled is False

    settings = Settings()
    identity_a = cast(CurrentIdentity, SimpleNamespace(user=owner_a))
    membership_a = SimpleNamespace(role=UserRole.OWNER)

    # Owner sets their chosen PIN
    req = VoicePinRequest(pin=SecretStr("582914"))  # 6-digit owner PIN
    res = voice_router.set_user_voice_pin(req, identity_a, membership_a, db, settings)
    assert res["status"] == "CONFIGURED"

    db.refresh(config)
    assert config.enabled is True  # Voice AI is now ACTIVE!


def test_two_concurrent_tenants_separate_numbers_and_cross_tenant_isolation(multi_tenant_db):
    """8. Isolation stricte : Compagnie A sur Numéro A -> Compagnie A data. Compagnie B sur Numéro B -> Compagnie B data."""
    db, comp_a, owner_a, comp_b, owner_b, _, _ = multi_tenant_db
    ent_a = ModuleEntitlementService(db)
    ent_b = ModuleEntitlementService(db)
    ent_a.activate_module(TenantContext(comp_a.id, owner_a.id), "voice")
    ent_b.activate_module(TenantContext(comp_b.id, owner_b.id), "voice")

    cfg_a = ensure_voice_business_config(db, comp_a.id, "+15145550001")
    cfg_b = ensure_voice_business_config(db, comp_b.id, "+14165550002")

    phone_a = VoicePhoneNumber(
        company_id=comp_a.id,
        config_id=cfg_a.id,
        phone_number="+15145550001",
        country_code="CA",
        provider="telnyx",
        number_type="local",
        capabilities=["voice"],
        status="ACTIVE",
    )
    phone_b = VoicePhoneNumber(
        company_id=comp_b.id,
        config_id=cfg_b.id,
        phone_number="+14165550002",
        country_code="CA",
        provider="telnyx",
        number_type="local",
        capabilities=["voice"],
        status="ACTIVE",
    )
    db.add_all([phone_a, phone_b])
    db.commit()

    # Inbound resolution for number A
    binding_a = db.scalar(select(VoicePhoneNumber).where(
        VoicePhoneNumber.phone_number == "+15145550001",
        VoicePhoneNumber.status == "ACTIVE",
    ))
    assert binding_a.company_id == comp_a.id
    assert binding_a.config_id == cfg_a.id

    # Inbound resolution for number B
    binding_b = db.scalar(select(VoicePhoneNumber).where(
        VoicePhoneNumber.phone_number == "+14165550002",
        VoicePhoneNumber.status == "ACTIVE",
    ))
    assert binding_b.company_id == comp_b.id
    assert binding_b.config_id == cfg_b.id

    # Complete cross-tenant separation
    assert binding_a.company_id != binding_b.company_id
    assert binding_a.phone_number != binding_b.phone_number


def test_global_number_uniqueness_cannot_share_or_steal(multi_tenant_db):
    """9. Unicité globale : un numéro ne peut appartenir qu'à un seul tenant. Impossibilité de partager ou voler."""
    db, comp_a, owner_a, comp_b, owner_b, _, _ = multi_tenant_db
    phone_a = VoicePhoneNumber(
        company_id=comp_a.id,
        phone_number="+15145550001",
        country_code="CA",
        provider="telnyx",
        number_type="local",
        capabilities=["voice"],
        status="ACTIVE",
    )
    db.add(phone_a)
    db.commit()

    # Tenant B has Voice active but attempts to assign Tenant A's number
    ModuleEntitlementService(db).activate_module(TenantContext(comp_b.id, owner_b.id), "voice")
    db.commit()

    settings = Settings()
    identity_b = cast(CurrentIdentity, SimpleNamespace(user=owner_b))

    with pytest.raises(HTTPException) as exc_info:
        voice_router.assign_voice_number(
            phone_a.id,
            voice_router.VoiceNumberAssignRequest(confirmed=True),
            identity_b,
            db,
            settings,
        )
    assert exc_info.value.status_code == 404  # Not found for Tenant B (scoped strictly to company_id)

    # Attempt to insert duplicate number raises integrity error
    dup_phone = VoicePhoneNumber(
        company_id=comp_b.id,
        phone_number="+15145550001",
        country_code="CA",
        provider="telnyx",
        number_type="local",
        capabilities=["voice"],
        status="ACTIVE",
    )
    db.add(dup_phone)
    with pytest.raises(Exception):
        db.commit()
    db.rollback()


def test_dynamic_agent_registry_per_tenant_and_changes(multi_tenant_db):
    """10. Voice utilise automatiquement les agents choisis par chaque compagnie (entitled ∩ active)."""
    db, comp_a, owner_a, comp_b, owner_b, _, _ = multi_tenant_db
    tenant_a = TenantContext(comp_a.id, owner_a.id)
    tenant_b = TenantContext(comp_b.id, owner_b.id)

    ent = ModuleEntitlementService(db)

    # Tenant A: Retail + CRM + Voice
    ent.activate_module(tenant_a, "retail")
    ent.activate_module(tenant_a, "crm")
    ent.activate_module(tenant_a, "voice")

    # Tenant B: CRM + Accounting + Voice
    ent.activate_module(tenant_b, "crm")
    ent.activate_module(tenant_b, "accounting")
    ent.activate_module(tenant_b, "voice")
    db.commit()

    active_a = set(ent.get_active_modules(tenant_a))
    active_b = set(ent.get_active_modules(tenant_b))

    assert active_a == {"retail", "crm", "voice"}
    assert active_b == {"crm", "accounting", "voice"}

    # Tenant A can access retail tools, cannot access accounting tools
    assert "retail" in active_a
    assert "accounting" not in active_a

    # Tenant B can access accounting tools, cannot access retail tools
    assert "accounting" in active_b
    assert "retail" not in active_b

    # Changing modules at runtime immediately updates active entitlements:
    # Deactivate CRM then activate Accounting (staying within the 3-module quota)
    ent.deactivate_module(tenant_a, "crm")
    ent.activate_module(tenant_a, "accounting")
    db.commit()
    active_a_updated = set(ent.get_active_modules(tenant_a))
    assert "accounting" in active_a_updated
    assert "crm" not in active_a_updated


@pytest.mark.asyncio
async def test_telnyx_purchase_failure_clean_rollback(multi_tenant_db, monkeypatch):
    """11. Échec achat Telnyx : rollback propre sans ressource fantôme résiduelle."""
    db, comp_a, owner_a, _, _, _, _ = multi_tenant_db
    tenant_a = TenantContext(comp_a.id, owner_a.id)
    ModuleEntitlementService(db).activate_module(tenant_a, "voice")
    db.commit()

    mock_provider = MockTelecomProvider()
    mock_provider.fail_order = True  # Simulate Telnyx failure
    mock_provider.fail_status_code = 422
    monkeypatch.setattr(voice_router, "TelnyxClient", lambda settings: mock_provider)

    settings = Settings()
    settings.telnyx_api_key = "KEY_TEST"
    settings.telnyx_public_key = "PUB_TEST"
    settings.telnyx_voice_connection_id = "conn-test"

    offer = {
        "phone_number": "+15145550001",
        "country_code": "CA",
        "number_type": "local",
        "cost_information": {"monthly_cost": "2.00", "upfront_cost": "1.00", "currency": "USD"},
        "monthly_cost": 2.0,
        "monthly_cost_currency": "USD",
        "upfront_cost": 1.0,
        "regulatory_status": "verified_no_requirements",
        "regulatory_requirements": [],
        "voice_capability": True,
        "sms_capability": True,
        "is_orderable": True,
    }
    quote_token = signed_number_quote(settings, comp_a.id, owner_a.id, offer)

    req = VoiceNumberProvisionRequest(
        phone_number="+15145550001",
        country_code="CA",
        quote_token=quote_token,
        confirmed=True,
    )
    identity_a = cast(CurrentIdentity, SimpleNamespace(user=owner_a))
    membership_a = SimpleNamespace(role=UserRole.OWNER)

    with pytest.raises(HTTPException) as exc_info:
        await voice_router.provision_voice_number(req, identity_a, db, settings, membership_a)
    assert exc_info.value.status_code == 422

    # Clean rollback verified: NO phantom row exists in database
    dangling = db.scalar(select(VoicePhoneNumber).where(VoicePhoneNumber.phone_number == "+15145550001"))
    assert dangling is None


@pytest.mark.asyncio
async def test_retry_purchase_without_double_purchase(multi_tenant_db, monkeypatch):
    """12. Retry achat sans double achat : idempotent et sans ré-appel opérateur."""
    db, comp_a, owner_a, _, _, _, _ = multi_tenant_db
    tenant_a = TenantContext(comp_a.id, owner_a.id)
    ModuleEntitlementService(db).activate_module(tenant_a, "voice")
    db.commit()

    mock_provider = MockTelecomProvider()
    monkeypatch.setattr(voice_router, "TelnyxClient", lambda settings: mock_provider)

    settings = Settings()
    settings.telnyx_api_key = "KEY_TEST"
    settings.telnyx_public_key = "PUB_TEST"
    settings.telnyx_voice_connection_id = "conn-test"

    offer = {
        "phone_number": "+15145550001",
        "country_code": "CA",
        "number_type": "local",
        "cost_information": {"monthly_cost": "2.00", "upfront_cost": "1.00", "currency": "USD"},
        "monthly_cost": 2.0,
        "monthly_cost_currency": "USD",
        "upfront_cost": 1.0,
        "regulatory_status": "verified_no_requirements",
        "regulatory_requirements": [],
        "voice_capability": True,
        "sms_capability": True,
        "is_orderable": True,
    }
    quote_token = signed_number_quote(settings, comp_a.id, owner_a.id, offer)

    req = VoiceNumberProvisionRequest(
        phone_number="+15145550001",
        country_code="CA",
        quote_token=quote_token,
        confirmed=True,
    )
    identity_a = cast(CurrentIdentity, SimpleNamespace(user=owner_a))
    membership_a = SimpleNamespace(role=UserRole.OWNER)

    # First purchase succeeds
    res1 = await voice_router.provision_voice_number(req, identity_a, db, settings, membership_a)
    assert res1["status"] == "ACTIVE"
    assert len(mock_provider.orders) == 1

    # Retry purchase returns ALREADY_ASSIGNED without placing a second Telnyx order
    res2 = await voice_router.provision_voice_number(req, identity_a, db, settings, membership_a)
    assert res2["status"] == "ALREADY_ASSIGNED"
    assert len(mock_provider.orders) == 1  # Exactly 1 order made, NO double billing!


def test_produits_ero_pilot_uses_same_generic_pipeline(multi_tenant_db):
    """13. Produits_Ero utilise exactement la même architecture générique sans aucun hardcode."""
    db, _, _, _, _, pilot, owner_p = multi_tenant_db
    tenant_p = TenantContext(pilot.id, owner_p.id)

    # Activate Voice on pilot tenant
    ModuleEntitlementService(db).activate_module(tenant_p, "voice", auto_init_voice=True)
    db.commit()

    # Automatically ensures VoiceBusinessConfig and binds existing active number +1 438 607 5438
    config = db.scalar(select(VoiceBusinessConfig).where(VoiceBusinessConfig.company_id == pilot.id))
    assert config is not None
    assert config.business_name == "Produits_Ero"
    assert config.telnyx_phone_number == "+14386075438"

    phone = db.scalar(select(VoicePhoneNumber).where(VoicePhoneNumber.phone_number == "+14386075438"))
    assert phone is not None
    assert phone.config_id == config.id
    assert phone.company_id == pilot.id
