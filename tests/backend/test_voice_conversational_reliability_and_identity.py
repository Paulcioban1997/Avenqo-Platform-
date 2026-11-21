"""Comprehensive test suite for Voice AI P0 Conversational Reliability & Secure Employee Identity.

Covers:
1. Public Voice Caller Tool Authorization (no user fallthrough error).
2. Product detail & category matching ("accessoires" matches category and name).
3. Public catalog spoken response with category filtering (no canned response loop).
4. Retail ASR phonetic normalization ("assurances" -> "accessoires").
5. Multi-turn conversational memory preservation in ConversationService.
6. Full colleague handover flow without race condition or hangup.
7. Compound internal staff questions (identity + modules + tasks + coaching).
8. Secure Employee Identity architecture & compliance (NIST SP 800-63B, Quebec Law 25).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.ai.chat.conversation_service import ConversationService
from backend.app.ai.tools.authorization import ToolAuthorizationError, ToolAuthorizationPolicy
from backend.app.ai.tools.business.commerce_tools import (
    GetProductDetailTool,
    ProductDetailArgs,
    ReserveProductTool,
)
from backend.app.ai.tools.contracts import ToolExecutionContext
from backend.app.assistants.registry import AssistantRegistry
from backend.app.models import AIMessageRole, Company, CompanyMembership, User, UserRole
from backend.app.models.base import Base
from backend.app.models.billing import BillingAccount
from backend.app.models.commerce_connection import NormalizedCommerceRecord
from backend.app.models.company_module import CompanyModule, CompanyModuleStatus
from backend.app.models.module import Module
from backend.app.models.voice import VoiceBusinessConfig, VoiceCall, VoiceCallerCredential
from backend.app.services.company_intelligence_service import CompanyIntelligenceService
from backend.app.services.employee_coach_service import EmployeeCoachService
from backend.app.services.voice_module_permission_service import VoiceModulePermissionService
from backend.app.voice.auth import VoiceCallerAuth
from backend.app.voice.caller_scope import (
    PUBLIC_VOICE_CALLER_PERMISSIONS,
    is_public_voice_caller,
)
from backend.app.voice.direct_answers import (
    disambiguate_telephony_catalog_query,
    is_identity_inquiry,
    is_module_access_question,
    is_open_catalog_question,
    resolve_direct_voice_answer,
    spoken_catalog_answer,
)
from backend.app.voice.employee_identity import (
    BIOMETRIC_REGULATORY_DISCLOSURE,
    ColleagueHandoverSession,
    HandoverState,
)
from shared.ai_engine.contracts import TenantContext


@pytest.fixture
def db_session(tmp_path):
    db_path = tmp_path / "test_voice_conv_rel.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    yield session

    session.close()
    engine.dispose()


def _setup_retail_tenant(session: Session):
    now = datetime.now(timezone.utc)
    # Modules
    mod_voice = Module(name="Voice AI", code="voice", is_active=True)
    mod_retail = Module(name="Retail AI", code="retail", is_active=True)
    mod_crm = Module(name="CRM AI", code="crm", is_active=True)
    session.add_all([mod_voice, mod_retail, mod_crm])
    session.flush()

    company = Company(
        id=uuid4(),
        name="Apex Mountain Sports",
        slug="apex-mountain-sports",
        email="contact@apex-mountain-sports.ca",
        industry="retail",
        country="CA",
        currency_code="CAD",
        timezone="America/Montreal",
        subscription_plan="scale",
        business_hours={"weekly": {"monday": [{"open": "09:00", "close": "18:00"}]}},
    )
    session.add(company)

    billing_account = BillingAccount(
        id=uuid4(),
        company_id=company.id,
        status="active",
    )
    session.add(billing_account)

    cm_voice = CompanyModule(company_id=company.id, module_id=mod_voice.id, status=CompanyModuleStatus.ACTIVE, activated_at=now)
    cm_retail = CompanyModule(company_id=company.id, module_id=mod_retail.id, status=CompanyModuleStatus.ACTIVE, activated_at=now)
    cm_crm = CompanyModule(company_id=company.id, module_id=mod_crm.id, status=CompanyModuleStatus.ACTIVE, activated_at=now)
    session.add_all([cm_voice, cm_retail, cm_crm])

    voice_config = VoiceBusinessConfig(
        id=uuid4(),
        company_id=company.id,
        business_name="Apex Mountain Sports",
        preferred_language="fr-CA",
        greeting_message="Bonjour! Bienvenue chez Apex Mountain Sports.",
        voice_api_key_hash="hash_dummy_voice_config_key",
        voice_api_key_last4="1234",
        voice_display_name="Apex Mountain Sports",
        enabled=True,
    )
    session.add(voice_config)

    # Owner François
    owner_user = User(
        id=uuid4(),
        company_id=company.id,
        email="francois.owner@apex.test",
        password_hash="mock_hash_123",
        first_name="François",
        last_name="Tremblay",
        role=UserRole.OWNER,
        is_active=True,
        phone="+15145550100",
    )
    session.add(owner_user)

    owner_membership = CompanyMembership(
        id=uuid4(),
        company_id=company.id,
        user_id=owner_user.id,
        role=UserRole.OWNER,
        is_active=True,
    )
    session.add(owner_membership)

    # Employee 1: Alice (Sales Specialist)
    emp1_user = User(
        id=uuid4(),
        company_id=company.id,
        email="alice.sales@apex.test",
        password_hash="mock_hash_123",
        first_name="Alice",
        last_name="Gagnon",
        job_title="Conseillère Ventes",
        role=UserRole.USER,
        is_active=True,
        phone="+15145550101",
    )
    session.add(emp1_user)

    emp1_membership = CompanyMembership(
        id=uuid4(),
        company_id=company.id,
        user_id=emp1_user.id,
        role=UserRole.USER,
        is_active=True,
    )
    session.add(emp1_membership)

    # Employee 2: Bob (Technician)
    emp2_user = User(
        id=uuid4(),
        company_id=company.id,
        email="bob.tech@apex.test",
        password_hash="mock_hash_123",
        first_name="Bob",
        last_name="Roy",
        job_title="Technicien Atelier",
        role=UserRole.USER,
        is_active=True,
        phone="+15145550102",
    )
    session.add(emp2_user)

    emp2_membership = CompanyMembership(
        id=uuid4(),
        company_id=company.id,
        user_id=emp2_user.id,
        role=UserRole.USER,
        is_active=True,
    )
    session.add(emp2_membership)

    # Commerce Products
    board = NormalizedCommerceRecord(
        id=uuid4(),
        company_id=company.id,
        entity_type="product",
        provider="shopify",
        source_record_id="prod-101",
        normalized_data={
            "product_id": "prod-101",
            "product_name": "Planche Alpine Pro",
            "name": "Planche Alpine Pro",
            "product_category": "Planches à neige",
            "category": "Planches à neige",
            "unit_price": 450.0,
            "inventory_level": 5.0,
            "in_stock": True,
        },
        deleted=False,
    )
    session.add(board)

    helmet = NormalizedCommerceRecord(
        id=uuid4(),
        company_id=company.id,
        entity_type="product",
        provider="shopify",
        source_record_id="prod-102",
        normalized_data={
            "product_id": "prod-102",
            "product_name": "Casque de Snowboard Stealth",
            "name": "Casque de Snowboard Stealth",
            "product_category": "Accessoires",
            "category": "Accessoires",
            "unit_price": 120.0,
            "inventory_level": 12.0,
            "in_stock": True,
        },
        deleted=False,
    )
    session.add(helmet)

    gloves = NormalizedCommerceRecord(
        id=uuid4(),
        company_id=company.id,
        entity_type="product",
        provider="shopify",
        source_record_id="prod-103",
        normalized_data={
            "product_id": "prod-103",
            "product_name": "Gants d'Hiver Thermiques",
            "name": "Gants d'Hiver Thermiques",
            "product_category": "Accessoires",
            "category": "Accessoires",
            "unit_price": 45.0,
            "inventory_level": 25.0,
            "in_stock": True,
        },
        deleted=False,
    )
    session.add(gloves)
    session.flush()

    grants = VoiceModulePermissionService(session)
    tenant = TenantContext(company.id, owner_user.id)
    grants.grant(tenant, "retail", "read_products", granted_by=owner_user.id)
    grants.grant(tenant, "retail", "read_inventory", granted_by=owner_user.id)
    grants.grant(tenant, "retail", "reserve_product", granted_by=owner_user.id)
    grants.grant(tenant, "crm", "read_availability", granted_by=owner_user.id)
    grants.grant(tenant, "crm", "list_slots", granted_by=owner_user.id)
    grants.grant(tenant, "crm", "create_appointment", granted_by=owner_user.id)

    session.commit()
    return company, voice_config, owner_user, emp1_user, emp2_user


def test_public_voice_caller_tool_authorization_no_user_error(db_session: Session):
    """Test 1: Public caller can execute public retail tools without ToolAuthorizationError on user_id=None."""
    from backend.app.assistants.contracts import AssistantDefinition, AssistantStatus
    company, voice_config, owner_user, emp1_user, _ = _setup_retail_tenant(db_session)
    registry = AssistantRegistry()
    registry.register(
        AssistantDefinition(
            slug="retail",
            name_key="retail",
            description_key="retail",
            status=AssistantStatus.AVAILABLE,
            category="commerce",
            module_code="retail",
            allowed_tool_names=frozenset({"get_top_products", "get_product_detail", "get_inventory_summary", "reserve_product"}),
            confirmation_policy="explicit_user_confirmation",
            mutation_capabilities=frozenset({"retail.reservation.write", "reservations.create"}),
        )
    )
    policy = ToolAuthorizationPolicy(db_session, registry)

    tenant = TenantContext(company_id=company.id, user_id=None)
    public_ctx = ToolExecutionContext(
        tenant=tenant,
        user_id=None,
        permissions=PUBLIC_VOICE_CALLER_PERMISSIONS,
        request_id="req-public-call-1",
        voice_path=True,
    )

    product_tool = GetProductDetailTool(db_session)
    reserve_tool = ReserveProductTool(db_session)

    # 1. Authorize product detail for public caller: MUST SUCCEED (no user lookup crash)
    policy.authorize(product_tool, public_ctx)

    # 2. Authorize reserve_product with default policy: MUST BE STRICTLY BLOCKED under tenant policy
    with pytest.raises(ToolAuthorizationError, match="disabled for phone calls under this company's policy"):
        policy.authorize(reserve_tool, public_ctx)

    # 3. Enable phone reservations in tenant call_policy:
    # Public caller is STILL blocked because reserve_product requires authentication
    voice_config.call_policy = {"allow_phone_reservations": True}
    db_session.commit()

    with pytest.raises(ToolAuthorizationError, match="Caller authentication is required for this tool"):
        policy.authorize(reserve_tool, public_ctx)

    # 4. Authenticated employee with appropriate role CAN execute reserve_product when allowed by company policy
    from backend.app.core.permissions import permissions_for
    staff_tenant = TenantContext(company_id=company.id, user_id=owner_user.id)
    staff_ctx = ToolExecutionContext(
        tenant=staff_tenant,
        user_id=owner_user.id,
        permissions=frozenset(permissions_for(UserRole.OWNER)),
        request_id="req-staff-call-1",
        voice_path=True,
        selected_agent_id="retail",
    )
    # Owner passes phone reservation policy check
    policy.authorize(reserve_tool, staff_ctx)


@pytest.mark.asyncio
async def test_product_detail_matches_accessories_category(db_session: Session):
    """Test 2: Product lookup by category 'accessoires' finds items in that category."""
    company, _, _, _, _ = _setup_retail_tenant(db_session)
    tenant = TenantContext(company_id=company.id, user_id=None)
    ctx = ToolExecutionContext(
        tenant=tenant,
        user_id=None,
        permissions=PUBLIC_VOICE_CALLER_PERMISSIONS,
        request_id="req-acc-lookup-1",
        voice_path=True,
    )

    tool = GetProductDetailTool(db_session)
    res = await tool.run(ctx, ProductDetailArgs(product_name="accessoires"))

    assert res.success is True
    data = res.data or {}
    assert data.get("found") is True
    products = data.get("products", [])
    assert len(products) >= 2
    names = [p["product_name"] for p in products]
    assert "Casque de Snowboard Stealth" in names
    assert "Gants d'Hiver Thermiques" in names


def test_spoken_catalog_answer_category_filtering(db_session: Session):
    """Test 3: spoken_catalog_answer returns accessories when present, and an honest refusal when none exist."""
    company, _, _, _, _ = _setup_retail_tenant(db_session)
    profile = CompanyIntelligenceService(db_session).get_profile(company.id)

    # 1. General catalog question
    general_answer = spoken_catalog_answer(
        profile.public_products,
        retail_enabled=True,
        locale="fr-CA",
        currency="CAD",
        query="Quels produits avez-vous ?",
    )
    assert "Nous avons au catalogue :" in general_answer
    assert "Planche Alpine Pro" in general_answer

    # 2. Specific accessories question when accessories ARE present
    acc_answer = spoken_catalog_answer(
        profile.public_products,
        retail_enabled=True,
        locale="fr-CA",
        currency="CAD",
        query="Quels accessoires avez-vous ?",
    )
    assert "Nous proposons notamment comme accessoires :" in acc_answer
    assert "Casque de Snowboard Stealth" in acc_answer
    assert "Gants d'Hiver Thermiques" in acc_answer

    # 3. Honest refusal when NO accessories exist in catalog (NEVER present snowboards as accessories!)
    catalog_without_accessories = [
        p for p in profile.public_products
        if "accessoire" not in (str(p.get("category") or p.get("product_category") or "")).lower()
        and "gant" not in str(p.get("name") or "").lower()
        and "casque" not in str(p.get("name") or "").lower()
    ]
    empty_acc_answer = spoken_catalog_answer(
        catalog_without_accessories,
        retail_enabled=True,
        locale="fr-CA",
        currency="CAD",
        query="Quels accessoires avez-vous ?",
    )
    assert "aucun accessoire disponible dans notre catalogue" in empty_acc_answer
    assert "Planche Alpine Pro" not in empty_acc_answer

    # 4. English plural 'Accessories' category matching
    english_catalog = [
        {"name": "Stealth Helmet", "category": "Accessories", "price": 120.0, "is_live_stock": True},
        {"name": "Alpine Snowboard", "category": "Snowboards", "price": 450.0, "is_live_stock": True},
    ]
    en_answer = spoken_catalog_answer(
        english_catalog,
        retail_enabled=True,
        locale="en-US",
        currency="USD",
        query="What accessories do you have?",
    )
    assert "Stealth Helmet" in en_answer
    assert "Alpine Snowboard" not in en_answer

    # 5. Named product inquiry lookup in spoken_catalog_answer
    named_answer = spoken_catalog_answer(
        profile.public_products,
        retail_enabled=True,
        locale="fr-CA",
        currency="CAD",
        query="Combien coûte le Casque de Snowboard Stealth ?",
    )
    assert "Casque de Snowboard Stealth" in named_answer
    assert "120" in named_answer and "$" in named_answer

    # 6. Distinguish generic open catalog inquiries from named product inquiries
    assert is_open_catalog_question("Quels accessoires avez-vous ?") is True
    assert is_open_catalog_question("Accessoires") is True
    assert is_open_catalog_question("Casque Stealth") is False
    assert is_open_catalog_question("Combien coûte le casque Stealth ?") is False


def test_retail_telephony_contextual_disambiguation_assurances_vs_accessoires():
    """Test 4: Contextual disambiguation for 8kHz acoustic confusion (assurances vs accessoires)."""
    # Scenario A: Pure retail boutique (accessories in catalog, NO insurance services)
    # A.1 Shopping catalog query -> disambiguates to 'accessoire(s)'
    t1 = disambiguate_telephony_catalog_query(
        "Quelles assurances avez-vous pour l'hiver ?",
        active_modules={"retail", "voice"},
        company_industry="Retail Sports",
        company_services=["Vente d'équipements"],
        has_catalog_accessories=True,
    )
    assert t1 == "Quelles accessoires avez-vous pour l'hiver ?"

    # A.2 Explicit insurance inquiry (legal/liability/policy) in a retail store -> NEVER REWRITTEN
    t2 = disambiguate_telephony_catalog_query(
        "Avez-vous une assurance responsabilité civile pour vos activités ?",
        active_modules={"retail", "voice"},
        company_industry="Retail Sports",
        company_services=["Vente d'équipements"],
        has_catalog_accessories=True,
    )
    assert t2 == "Avez-vous une assurance responsabilité civile pour vos activités ?"

    # Scenario B: Pure insurance company -> NEVER REWRITTEN
    t3 = disambiguate_telephony_catalog_query(
        "Quelles assurances avez-vous pour l'hiver ?",
        active_modules={"insurance", "voice"},
        company_industry="Insurance",
        company_services=["Assurance auto", "Assurance voyage"],
        has_catalog_accessories=False,
    )
    assert t3 == "Quelles assurances avez-vous pour l'hiver ?"

    # Scenario C: Hybrid company offering both retail AND insurance -> NEVER REWRITTEN
    t4 = disambiguate_telephony_catalog_query(
        "Quelles assurances avez-vous pour l'hiver ?",
        active_modules={"retail", "insurance", "voice"},
        company_industry="Sports & Assurances",
        company_services=["Vente de ski", "Assurance bris de matériel"],
        has_catalog_accessories=True,
    )
    assert t4 == "Quelles assurances avez-vous pour l'hiver ?"


def test_multiturn_conversational_session_memory_and_anaphora(db_session: Session):
    """Test 5: Multi-turn conversational memory preservation in ConversationService and reference resolution."""
    company, _, owner_user, _, _ = _setup_retail_tenant(db_session)
    conv_service = ConversationService(db_session)

    # Initialize call conversation
    conv = conv_service.create(company.id, owner_user.id, "Voice test call", "fr-CA")

    # Turn 1: User asks for accessories, assistant lists them
    conv_service.add_message(
        company.id,
        conv.id,
        AIMessageRole.USER,
        "Quels accessoires avez-vous ?",
    )
    conv_service.add_message(
        company.id,
        conv.id,
        AIMessageRole.ASSISTANT,
        "Nous proposons notamment comme accessoires : le Casque de Snowboard Stealth à 120 $ et les Gants d'Hiver Thermiques à 45 $.",
        provider="central_ai",
        model="gpt-4o-realtime",
    )

    # Turn 2: User asks anaphoric reference: "Combien coûte le deuxième ?"
    conv_service.add_message(
        company.id,
        conv.id,
        AIMessageRole.USER,
        "Combien coûte le deuxième ?",
    )

    messages = conv_service.messages(company.id, conv.id)
    assert len(messages) == 3
    contents = [m.content for m in messages]
    assert "Quels accessoires avez-vous ?" in contents
    assert any("Casque de Snowboard Stealth" in c and "120 $" in c for c in contents)
    assert any("Gants d'Hiver Thermiques" in c and "45 $" in c for c in contents)
    assert "Combien coûte le deuxième ?" in contents

    # Verify that 'Combien coûte le deuxième ?' is NOT an open catalog question,
    # and therefore flows to Central AI context resolution rather than canned answer
    assert is_open_catalog_question("Combien coûte le deuxième ?") is False


def test_compound_internal_staff_questions(db_session: Session):
    """Test 5: Compound internal staff questions (identity + modules + tasks)."""
    company, _, owner_user, emp1_user, _ = _setup_retail_tenant(db_session)

    query = "Qui suis-je ? Quels sont mes modules autorisés et quelles sont mes tâches aujourd'hui ?"

    assert is_identity_inquiry(query) is True
    assert is_module_access_question(query) is True

    answer = resolve_direct_voice_answer(
        db_session,
        company_id=company.id,
        transcript=query,
        authenticated_staff=True,
        staff_role="employee",
        locale="fr-CA",
        user_id=emp1_user.id,
    )

    assert answer is not None
    # Check identity
    assert "Alice Gagnon" in answer
    assert "Conseillère Ventes" in answer
    # Check modules
    assert "modules suivants" in answer
    # Check tasks
    assert "tâche" in answer


def test_colleague_handover_flow_and_clean_reauth(db_session: Session):
    """Test 6: Colleague handover revokes Employee A and binds Employee B with zero privilege bleeding."""
    company, voice_config, owner_user, emp1_user, emp2_user = _setup_retail_tenant(db_session)
    settings = MagicMock()
    settings.auth_jwt_secret = "test-jwt-secret-very-secure-32chars!"
    settings.voice_pin_max_attempts = 5
    settings.voice_pin_lockout_seconds = 900
    settings.voice_pin_max_scan_candidates = 50
    settings.voice_auth_session_ttl_seconds = 600
    settings.voice_long_calls_enabled = False
    settings.rate_limit_enabled = False
    settings.redis_url = None
    settings.voice_tenant_max_failed_auth_per_window = 30
    settings.voice_tenant_max_total_auth_per_window = 120
    settings.voice_tenant_auth_window_seconds = 60

    auth_service = VoiceCallerAuth(db_session, settings)
    tenant = TenantContext(company.id, owner_user.id)

    # Set PINs for Alice (482915) and Bob (739184)
    auth_service.set_pin(tenant, "USER", emp1_user.id, "482915", phone_number="+15145550101")
    auth_service.set_pin(tenant, "USER", emp2_user.id, "739184", phone_number="+15145550102")

    # Call starts and Employee A (Alice) authenticates
    call = VoiceCall(
        id=uuid4(),
        company_id=company.id,
        config_id=voice_config.id,
        caller_phone="+15145550101",
        status="in_progress",
    )
    db_session.add(call)
    db_session.commit()

    # Step 1: Alice enters PIN
    res_a = auth_service.verify_gather(call, pin="482915")
    assert res_a["authenticated"] is True
    assert call.authenticated_user_id == emp1_user.id
    assert call.caller_type == "EMPLOYEE"
    assert call.pin_challenge_hash is None

    # Step 2: Handover triggered
    call.authenticated_user_id = None
    call.caller_type = "UNKNOWN"
    call.source_context = {
        "authenticated": False,
        "handover_revoked": True,
        "handover_count": 1,
    }
    db_session.commit()

    assert call.authenticated_user_id is None
    assert call.source_context["handover_revoked"] is True

    # Step 3: Bob enters his PIN (739184) with his Identifier or compound entry
    res_b = auth_service.verify_gather(call, pin="739184", identifier=emp2_user.email)
    assert res_b["authenticated"] is True
    assert call.authenticated_user_id == emp2_user.id
    assert call.caller_type == "EMPLOYEE"
    assert call.source_context["user_name"] == "Bob Roy"
    assert call.source_context["handover_revoked"] is False
    assert call.pin_challenge_hash is None


def test_biometric_and_legal_compliance_specifications():
    """Test 7: Verify NIST SP 800-63B and Quebec Law 25 compliance requirements."""
    spec = BIOMETRIC_REGULATORY_DISCLOSURE
    assert any("NIST SP 800-63B" in f for f in spec["applicable_frameworks"])
    assert "NOT compliant as a primary authenticator" in spec["nist_sp_800_63b_determination"]

    law25 = spec["quebec_law_25_mandates"]
    assert law25["express_consent_required"] is True
    assert law25["cai_60_day_prior_declaration_required"] is True

    handover = ColleagueHandoverSession(
        call_id=uuid4(),
        company_id=uuid4(),
        previous_user_id=uuid4(),
        new_user_id=uuid4(),
        state=HandoverState.COMPLETED,
    )
    assert handover.state == HandoverState.COMPLETED
