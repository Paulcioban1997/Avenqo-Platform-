"""Tests for Avenqo Voice AI TTS pronunciation, dynamic Retail sync, and multi-tenant isolation.

Covers:
1. Custom pronunciation in IVR, greeting, and Central AI context without technical slugs.
2. Voice display name modification preserving company_slug and company.name.
3. Live Retail catalog freshness: product addition, price modification, stock changes, archiving, and deletion.
4. Strict multi-tenant isolation between two companies with different catalogs and prices.
5. Zero-hallucination website policy: honest refusal when unconfigured, verified URL when configured.
6. Module authorization enforcement: unauthorized modules strictly blocked.
7. Customization API endpoint contracts for voice_display_name and voice_pronunciation.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.config.settings import Settings
from backend.app.dependencies.auth import CurrentIdentity
from backend.app.models import (
    Base,
    BillingAccount,
    Company,
    CompanyMembership,
    CompanyModule,
    CompanyModuleStatus,
    Module,
    NormalizedCommerceRecord,
    User,
    UserRole,
    VoiceBusinessConfig,
    VoiceCall,
)
from backend.app.models.crm import CRMService
from backend.app.routers.voice import (
    get_voice_customization,
    update_voice_customization,
)
from backend.app.schemas.voice import (
    VoiceCustomizationUpdateRequest,
)
from backend.app.services.company_intelligence_service import CompanyIntelligenceService
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from backend.app.voice.service import VoiceOrchestrator, _api_key_hash
from backend.app.voice.telnyx_media import PublicInboundConversation
from backend.app.voice.tool_registry import VoiceToolRegistryService
from backend.app.ai.chat.chat_service import _localized_system_instruction, SYSTEM_INSTRUCTION
from shared.ai_engine.contracts import TenantContext


def _setup_multi_tenant_db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'voice-sync-test.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)

    # Initialize standard modules
    modules = [
        Module(name="Voice AI", code="voice", is_active=True),
        Module(name="Retail AI", code="retail", is_active=True),
        Module(name="CRM AI", code="crm", is_active=True),
        Module(name="Accounting AI", code="accounting", is_active=True),
    ]
    session.add_all(modules)
    session.flush()

    # Company A: Produits_Ero (e-commerce snowboard brand)
    company_a = Company(
        name="Produits_Ero",
        slug="produits-ero",
        email="owner@produits-ero.example.com",
        country="CA",
        timezone="America/Toronto",
        industry="Retail",
        subscription_plan="professional",
        currency_code="CAD",
        website=None,  # No website configured initially
    )
    # Company B: Auto_Garage_Pro (automotive garage)
    company_b = Company(
        name="Auto_Garage_Pro",
        slug="auto-garage-pro",
        email="owner@autogaragepro.example.com",
        country="CA",
        timezone="America/Toronto",
        industry="Automotive",
        subscription_plan="professional",
        currency_code="CAD",
        website="https://autogaragepro.ca",
    )
    session.add_all([company_a, company_b])
    session.flush()

    # Users / Memberships
    user_a = User(company_id=company_a.id, first_name="Ero", last_name="Owner", email="ero@example.com", password_hash="hash", role=UserRole.OWNER, is_active=True)
    user_b = User(company_id=company_b.id, first_name="Auto", last_name="Owner", email="auto@example.com", password_hash="hash", role=UserRole.OWNER, is_active=True)
    session.add_all([user_a, user_b])
    session.flush()

    session.add_all([
        CompanyMembership(company_id=company_a.id, user_id=user_a.id, role=UserRole.OWNER, is_active=True),
        CompanyMembership(company_id=company_b.id, user_id=user_b.id, role=UserRole.OWNER, is_active=True),
        BillingAccount(company_id=company_a.id, plan_code="professional", status="active"),
        BillingAccount(company_id=company_b.id, plan_code="professional", status="active"),
    ])

    # Activate Voice and Retail for Company A
    entitlements_a = ModuleEntitlementService(session)
    entitlements_a.activate_module(TenantContext(company_a.id), "voice", auto_init_voice=False)
    entitlements_a.activate_module(TenantContext(company_a.id), "retail", auto_init_voice=False)

    # Activate Voice and CRM for Company B (no retail, no accounting)
    entitlements_b = ModuleEntitlementService(session)
    entitlements_b.activate_module(TenantContext(company_b.id), "voice", auto_init_voice=False)
    entitlements_b.activate_module(TenantContext(company_b.id), "crm", auto_init_voice=False)

    # Voice configs
    config_a = VoiceBusinessConfig(
        company_id=company_a.id,
        business_name="Produits_Ero",
        voice_display_name="Produits Ero",
        custom_pronunciation="Produits Ero",
        timezone_name="America/Toronto",
        opening_hours={"monday": {"open": "09:00", "close": "18:00"}},
        services=[],
        preferred_language="fr",
        greeting_message="Bonjour, bienvenue chez Produits Ero.",
        voice_api_key_hash=_api_key_hash("key_a"),
        voice_api_key_last4="keya",
        enabled=True,
    )
    config_b = VoiceBusinessConfig(
        company_id=company_b.id,
        business_name="Auto_Garage_Pro",
        voice_display_name="Garage Pro",
        custom_pronunciation="Garage Pro",
        timezone_name="America/Toronto",
        opening_hours={"monday": {"open": "08:00", "close": "17:00"}},
        services=[{"name": "Vidange d'huile", "duration_minutes": 45, "price": 89.99, "currency": "CAD"}],
        preferred_language="fr",
        greeting_message="Bonjour, bienvenue chez Garage Pro.",
        voice_api_key_hash=_api_key_hash("key_b"),
        voice_api_key_last4="keyb",
        enabled=True,
    )
    crm_service_b = CRMService(
        company_id=company_b.id,
        name="Vidange d'huile",
        duration_minutes=45,
        price=89.99,
        currency="CAD",
        is_active=True,
        is_approved_by_owner=True,
        is_published=True,
    )
    session.add_all([config_a, config_b, crm_service_b])
    session.commit()

    return engine, session, company_a, config_a, user_a, company_b, config_b, user_b


def test_effective_voice_name_and_pronunciation_formatting(tmp_path):
    engine, session, company_a, config_a, user_a, company_b, config_b, user_b = _setup_multi_tenant_db(tmp_path)
    try:
        # 1. Config A: Custom pronunciation "Produits Ero"
        assert config_a.effective_voice_name == "Produits Ero"

        # 2. If custom_pronunciation is JSON dictionary
        config_a.custom_pronunciation = json.dumps({"company": "Produits Ero Sport"})
        assert config_a.effective_voice_name == "Produits Ero Sport"

        # 3. If custom_pronunciation is empty but voice_display_name is set
        config_a.custom_pronunciation = None
        config_a.voice_display_name = "Produits Ero Boutique"
        assert config_a.effective_voice_name == "Produits Ero Boutique"

        # 4. Fallback: if neither is set, replace underscores and hyphens (never pronounce tiret bas)
        config_a.voice_display_name = None
        config_a.business_name = "Produits_Ero"
        assert config_a.effective_voice_name == "Produits Ero"
        assert "_" not in config_a.effective_voice_name

        # 5. Profile context outputs clean spoken name
        profile_a = CompanyIntelligenceService(session).get_profile(company_a.id)
        assert profile_a.voice_display_name == "Produits Ero"
        ctx = profile_a.as_context(public=True)
        assert ctx["voice_display_name"] == "Produits Ero"
    finally:
        session.close()
        engine.dispose()


def test_changing_voice_name_preserves_technical_slug_and_company_name(tmp_path):
    engine, session, company_a, config_a, user_a, company_b, config_b, user_b = _setup_multi_tenant_db(tmp_path)
    try:
        settings = Settings()
        identity = cast(CurrentIdentity, SimpleNamespace(user=user_a))

        # Update voice display name via customization endpoint
        update_req = VoiceCustomizationUpdateRequest(
            voice_display_name="Produits Ero Neige & Montagne",
            voice_pronunciation="Produits Ero Neige & Montagne",
        )
        res = update_voice_customization(update_req, identity=identity, db=session, settings=settings)

        assert res.voice_display_name == "Produits Ero Neige & Montagne"
        assert res.voice_pronunciation == "Produits Ero Neige & Montagne"

        # Re-query DB to verify stability of technical slug and business name
        session.refresh(company_a)
        session.refresh(config_a)

        assert company_a.slug == "produits-ero"  # Technical slug MUST remain untouched!
        assert company_a.name == "Produits_Ero"  # DB company name MUST remain untouched!
        assert config_a.voice_display_name == "Produits Ero Neige & Montagne"
        assert config_a.effective_voice_name == "Produits Ero Neige & Montagne"
    finally:
        session.close()
        engine.dispose()


def test_dynamic_retail_product_addition_and_immediate_voice_freshness(tmp_path):
    engine, session, company_a, config_a, user_a, company_b, config_b, user_b = _setup_multi_tenant_db(tmp_path)
    try:
        intel = CompanyIntelligenceService(session)

        # Initially, Company A has no products
        profile_init = intel.get_profile(company_a.id)
        assert len(profile_init.public_products) == 0

        # Step 1: Owner adds a new snowboard in Retail
        snowboard_1 = NormalizedCommerceRecord(
            company_id=company_a.id,
            connection_id=uuid4(),
            provider="shopify",
            entity_type="products",
            source_record_id="prod_snow_101",
            deleted=False,
            normalized_data={
                "product_name": "The Hidden Snowboard",
                "product_category": "Snowboards",
                "unit_price": 749.95,
                "inventory_level": 10,
                "in_stock": True,
                "description": "Planche à neige haut de gamme tout-terrain.",
            },
        )
        session.add(snowboard_1)
        session.commit()

        # Step 2: Voice immediately reflects the new product on the very next query
        profile_after_add = intel.get_profile(company_a.id)
        assert len(profile_after_after := profile_after_add.public_products) == 1
        p = profile_after_after[0]
        assert p["name"] == "The Hidden Snowboard"
        assert p["price"] == 749.95
        assert p["in_stock"] is True
        assert p["inventory_count"] == 10

        # Step 3: Tool get_business_info immediately returns the verified product
        call_a = VoiceCall(
            company_id=config_a.company_id,
            config_id=config_a.id,
            telnyx_call_control_id="cc-test",
            caller_phone="+15145550001",
            caller_type="CLIENT",
            status="in_progress",
        )
        session.add(call_a)
        session.commit()
        orchestrator = VoiceOrchestrator(session, Settings())
        tool_res = asyncio.run(orchestrator.execute_tool(config_a, "cc-test", "action-1", "get_business_info", {}))
        assert tool_res["success"] is True
        assert len(tool_res["products"]) == 1
        assert tool_res["products"][0]["name"] == "The Hidden Snowboard"
        assert tool_res["products"][0]["price"] == 749.95
    finally:
        session.close()
        engine.dispose()


def test_dynamic_retail_price_modification_reflects_instantly(tmp_path):
    engine, session, company_a, config_a, user_a, company_b, config_b, user_b = _setup_multi_tenant_db(tmp_path)
    try:
        intel = CompanyIntelligenceService(session)

        # Create product with initial price 749.95
        product = NormalizedCommerceRecord(
            company_id=company_a.id,
            connection_id=uuid4(),
            provider="shopify",
            entity_type="product",  # Supports singular "product" entity type
            source_record_id="prod_snow_102",
            deleted=False,
            normalized_data={
                "product_name": "Snowboard Alpin Pro",
                "unit_price": 749.95,
                "inventory_level": 5,
                "in_stock": True,
            },
        )
        session.add(product)
        session.commit()

        # Check initial price
        p_init = intel.get_profile(company_a.id).public_products[0]
        assert p_init["price"] == 749.95

        # Owner modifies price from 749.95 to 699.95
        product.normalized_data = {
            "product_name": "Snowboard Alpin Pro",
            "unit_price": 699.95,
            "inventory_level": 5,
            "in_stock": True,
        }
        session.commit()

        # Immediate next turn query returns 699.95 without retraining
        p_updated = intel.get_profile(company_a.id).public_products[0]
        assert p_updated["price"] == 699.95

        # get_business_info returns 699.95
        call_price = VoiceCall(
            company_id=config_a.company_id,
            config_id=config_a.id,
            telnyx_call_control_id="cc-test-price",
            caller_phone="+15145550001",
            caller_type="CLIENT",
            status="in_progress",
        )
        session.add(call_price)
        session.commit()
        orchestrator = VoiceOrchestrator(session, Settings())
        tool_res = asyncio.run(orchestrator.execute_tool(config_a, "cc-test-price", "action-2", "get_business_info", {}))
        assert tool_res["products"][0]["price"] == 699.95
    finally:
        session.close()
        engine.dispose()


def test_dynamic_retail_stock_modification_and_out_of_stock_state(tmp_path):
    engine, session, company_a, config_a, user_a, company_b, config_b, user_b = _setup_multi_tenant_db(tmp_path)
    try:
        intel = CompanyIntelligenceService(session)

        product = NormalizedCommerceRecord(
            company_id=company_a.id,
            connection_id=uuid4(),
            provider="shopify",
            entity_type="products",
            source_record_id="prod_snow_103",
            deleted=False,
            normalized_data={
                "product_name": "Snowboard Freestyle Limitée",
                "unit_price": 899.00,
                "inventory_level": 8,
                "in_stock": True,
            },
        )
        session.add(product)
        session.commit()

        assert intel.get_profile(company_a.id).public_products[0]["in_stock"] is True
        assert intel.get_profile(company_a.id).public_products[0]["inventory_count"] == 8

        # Owner marks stock as 0 (stock épuisé)
        product.normalized_data = {
            "product_name": "Snowboard Freestyle Limitée",
            "unit_price": 899.00,
            "inventory_level": 0,
            "in_stock": False,
        }
        session.commit()

        # Immediately indicates out of stock
        p_out = intel.get_profile(company_a.id).public_products[0]
        assert p_out["in_stock"] is False
        assert p_out["inventory_count"] == 0
    finally:
        session.close()
        engine.dispose()


def test_dynamic_retail_product_deletion_and_archive_filtering(tmp_path):
    engine, session, company_a, config_a, user_a, company_b, config_b, user_b = _setup_multi_tenant_db(tmp_path)
    try:
        intel = CompanyIntelligenceService(session)

        prod_active = NormalizedCommerceRecord(
            company_id=company_a.id,
            connection_id=uuid4(),
            provider="shopify",
            entity_type="products",
            source_record_id="prod_active_1",
            deleted=False,
            normalized_data={"product_name": "Snowboard Actif", "unit_price": 500.0, "inventory_level": 10},
        )
        prod_to_delete = NormalizedCommerceRecord(
            company_id=company_a.id,
            connection_id=uuid4(),
            provider="shopify",
            entity_type="products",
            source_record_id="prod_del_2",
            deleted=False,
            normalized_data={"product_name": "Snowboard Retiré", "unit_price": 400.0, "inventory_level": 5},
        )
        prod_archived = NormalizedCommerceRecord(
            company_id=company_a.id,
            connection_id=uuid4(),
            provider="shopify",
            entity_type="products",
            source_record_id="prod_arch_3",
            deleted=False,
            normalized_data={"product_name": "Snowboard Archivé", "unit_price": 450.0, "status": "archived"},
        )
        session.add_all([prod_active, prod_to_delete, prod_archived])
        session.commit()

        # Archived product is excluded immediately
        prods = intel.get_profile(company_a.id).public_products
        names = [p["name"] for p in prods]
        assert "Snowboard Actif" in names
        assert "Snowboard Retiré" in names
        assert "Snowboard Archivé" not in names  # Archived MUST be excluded!

        # Now mark prod_to_delete as deleted = True (Shopify deletion webhook)
        prod_to_delete.deleted = True
        session.commit()

        prods_after = intel.get_profile(company_a.id).public_products
        names_after = [p["name"] for p in prods_after]
        assert "Snowboard Actif" in names_after
        assert "Snowboard Retiré" not in names_after  # Deleted MUST be excluded!
        assert len(prods_after) == 1
    finally:
        session.close()
        engine.dispose()


def test_strict_multi_tenant_isolation_between_two_distinct_companies(tmp_path):
    engine, session, company_a, config_a, user_a, company_b, config_b, user_b = _setup_multi_tenant_db(tmp_path)
    try:
        intel = CompanyIntelligenceService(session)

        # Company A has snowboards
        session.add(NormalizedCommerceRecord(
            company_id=company_a.id,
            connection_id=uuid4(),
            provider="shopify",
            entity_type="products",
            source_record_id="prod_a",
            deleted=False,
            normalized_data={"product_name": "The Hidden Snowboard", "unit_price": 749.95, "inventory_level": 10},
        ))
        session.commit()

        # Company B has automotive services, no snowboards
        profile_a = intel.get_profile(company_a.id)
        profile_b = intel.get_profile(company_b.id)

        # 1. Company A check
        assert profile_a.business_name == "Produits_Ero"
        assert profile_a.voice_display_name == "Produits Ero"
        assert len(profile_a.public_products) == 1
        assert profile_a.public_products[0]["name"] == "The Hidden Snowboard"
        assert len(profile_a.configured_crm_services) == 0

        # 2. Company B check
        assert profile_b.business_name == "Auto_Garage_Pro"
        assert profile_b.voice_display_name == "Garage Pro"
        assert len(profile_b.public_products) == 0  # No snowboards!
        assert len(profile_b.configured_crm_services) == 1
        assert profile_b.configured_crm_services[0]["name"] == "Vidange d'huile"

        # 3. Price modification in Company A never affects Company B
        prod_a = session.scalar(select(NormalizedCommerceRecord).where(NormalizedCommerceRecord.company_id == company_a.id))
        assert prod_a is not None
        prod_a.normalized_data = {"product_name": "The Hidden Snowboard", "unit_price": 699.95, "inventory_level": 10}
        session.commit()

        profile_b_fresh = intel.get_profile(company_b.id)
        assert len(profile_b_fresh.public_products) == 0
        assert profile_b_fresh.configured_crm_services[0]["price"] == 89.99
    finally:
        session.close()
        engine.dispose()


def test_zero_hallucinated_website_policy_in_prompt_and_profile(tmp_path):
    engine, session, company_a, config_a, user_a, company_b, config_b, user_b = _setup_multi_tenant_db(tmp_path)
    try:
        intel = CompanyIntelligenceService(session)

        # Company A: website is None
        profile_a = intel.get_profile(company_a.id)
        assert profile_a.website is None
        ctx_a = profile_a.as_context(public=True)
        assert ctx_a["website"] is None

        # Check system prompt includes the exact zero-fabrication instruction
        instruction = _localized_system_instruction(
            SYSTEM_INSTRUCTION,
            user_language="fr-CA",
            company_country="CA",
            company_currency="CAD",
            company_timezone="America/Toronto",
            is_voice_call=True,
        )
        assert "ZERO-FABRICATION COMMERCIAL ACCURACY" in instruction
        assert "Je ne dispose pas actuellement d'une adresse de boutique en ligne confirmée." in instruction
        assert "company_profile.website" in instruction

        # Company B: website is configured and verified
        profile_b = intel.get_profile(company_b.id)
        assert profile_b.website == "https://autogaragepro.ca"
        ctx_b = profile_b.as_context(public=True)
        assert ctx_b["website"] == "https://autogaragepro.ca"
    finally:
        session.close()
        engine.dispose()


def test_unauthorized_module_data_strictly_blocked(tmp_path):
    engine, session, company_a, config_a, user_a, company_b, config_b, user_b = _setup_multi_tenant_db(tmp_path)
    try:
        # Company A only has Voice and Retail (no accounting, no marketing)
        active_a = ModuleEntitlementService(session).get_active_modules(TenantContext(company_a.id))
        assert "accounting" not in active_a
        assert "marketing" not in active_a
        assert "retail" in active_a

        # AssistantRegistry / tools check
        from backend.app.assistants.registry import build_default_assistant_registry
        registry = build_default_assistant_registry()
        tool_service = VoiceToolRegistryService(session, registry)

        allowed_tools, _ = tool_service.allowed_tools(
            TenantContext(company_a.id),
            permissions=frozenset({"voice:public_caller", "ai:use"}),
            active_modules=frozenset(active_a),
        )

        # Accounting and confidential management tools must NEVER be exposed
        assert "get_unpaid_invoices" not in allowed_tools
        assert "get_accounting_audit" not in allowed_tools
        assert "create_campaign" not in allowed_tools
    finally:
        session.close()
        engine.dispose()

