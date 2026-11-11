"""Tests pour l'architecture universelle multi-tenant et multi-sources d'Avenqo Central + Voice.

Vérifie:
1. Découverte dynamique des sources et capacités à l'exécution pour deux entreprises de secteurs distincts :
   - Tenant A : Commerce / Retail (Produits Éro) avec catalogue, stock et réservation en magasin.
   - Tenant B : Services professionnels / Juridique (Cabinet Juridique Lex) avec consultations CRM,
     documents de politiques internes (RAG), et AUCUN module Retail.
2. Outil ReserveProductTool :
   - Demande de confirmation préalable.
   - Réservation confirmée avec code référence unique (RES-...).
   - Distinction explicite : mise de côté en boutique sans blocage de stock distant électronique.
   - Refus strict si produit en rupture de stock ou quantité supérieure au stock.
3. Précédence des sources et arbitrage des conflits (SourcePrecedenceService).
4. Cloisonnement strict multi-tenant et garde d'autorisation pour appelants publics :
   - Appelant public autorisé sur les outils publics activés du tenant (info, CRM booking, retail si actif, documents si présents).
   - Appelant public strictement bloqué sur les outils privés (ventes, marge, impayés, leads).
   - Appelant public du Tenant B (non-retail) strictement bloqué sur les outils Retail.
5. Neutralité du prompt d'orchestration (chat_service) et résolution des dates relatives.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from uuid import UUID, uuid4
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.assistants.registry import AssistantRegistry
from backend.app.ai.chat.chat_service import _localized_system_instruction, SYSTEM_INSTRUCTION
from backend.app.ai.tools.authorization import ToolAuthorizationPolicy
from backend.app.ai.tools.business.commerce_tools import (
    GetProductDetailTool,
    ProductDetailArgs,
    ReserveProductArgs,
    ReserveProductTool,
)
from backend.app.ai.tools.business.crm_tools import (
    CheckAvailabilityArgs,
    CheckAvailabilityTool,
    CreateAppointmentArgs,
    CreateAppointmentTool,
)
from backend.app.ai.tools.business.sales_tools import GetSalesSummaryTool
from backend.app.ai.tools.contracts import ToolExecutionContext
from backend.app.ai.tools.exceptions import ToolAuthorizationError
from backend.app.models import (
    Base,
    Company,
    CompanyMembership,
    CompanyModule,
    CompanyModuleStatus,
    Module,
    NormalizedCommerceRecord,
    User,
    UserRole,
    VoiceBusinessConfig,
    VoiceModulePermission,
)
from backend.app.models.crm import CRMAppointment, CRMService
from backend.app.models.workspace import TenantDocument
from backend.app.services.company_intelligence_service import CompanyIntelligenceService
from backend.app.services.source_precedence_service import (
    SourceFreshnessStatus,
    SourcePrecedenceCategory,
    SourcePrecedenceService,
)
from backend.app.voice.caller_scope import (
    PUBLIC_VOICE_CALLER_PERMISSION,
    PUBLIC_VOICE_CALLER_PERMISSIONS,
    is_public_voice_caller,
    public_voice_tool_allowed,
)
from shared.ai_engine.contracts import TenantContext


def _create_test_db(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'universal-voice-arch.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)

    # 1. Modules
    modules = [
        Module(name="Voice AI", code="voice", is_active=True),
        Module(name="Retail AI", code="retail", is_active=True),
        Module(name="CRM AI", code="crm", is_active=True),
        Module(name="OCR & Documents", code="ocr", is_active=True),
        Module(name="Accounting AI", code="accounting", is_active=True),
    ]
    session.add_all(modules)
    session.flush()

    # 2. Tenant A: Retail (Produits Éro)
    company_a = Company(
        id=uuid4(),
        name="Produits_Ero",
        slug="produits-ero",
        email="contact@produits-ero.example.com",
        country="CA",
        timezone="America/Toronto",
        industry="Commerce de détail et sport",
        subscription_plan="professional",
        currency_code="CAD",
        website="https://produits-ero.ca",
        business_hours={
            "monday": [{"start": "09:00", "end": "18:00"}],
            "tuesday": [{"start": "09:00", "end": "18:00"}],
            "wednesday": [{"start": "09:00", "end": "18:00"}],
            "thursday": [{"start": "09:00", "end": "20:00"}],
            "friday": [{"start": "09:00", "end": "20:00"}],
            "saturday": [{"start": "10:00", "end": "17:00"}],
            "sunday": [],
        },
    )
    user_a = User(
        id=uuid4(),
        company_id=company_a.id,
        first_name="Francis",
        last_name="Queval",
        email="owner@produits-ero.example.com",
        password_hash="fake-hash",
        role=UserRole.ADMIN,
        is_active=True,
    )
    session.add_all([company_a, user_a])
    session.flush()

    member_a = CompanyMembership(
        id=uuid4(),
        company_id=company_a.id,
        user_id=user_a.id,
        role="owner",
        is_active=True,
    )
    now = datetime.now(timezone.utc)
    # Modules A: voice, crm, retail
    mod_a_voice = CompanyModule(company_id=company_a.id, module_id=modules[0].id, status=CompanyModuleStatus.ACTIVE, activated_at=now)
    mod_a_retail = CompanyModule(company_id=company_a.id, module_id=modules[1].id, status=CompanyModuleStatus.ACTIVE, activated_at=now)
    mod_a_crm = CompanyModule(company_id=company_a.id, module_id=modules[2].id, status=CompanyModuleStatus.ACTIVE, activated_at=now)
    config_a = VoiceBusinessConfig(
        id=uuid4(),
        company_id=company_a.id,
        business_name="Produits Éro",
        voice_display_name="Produits Éro",
        custom_pronunciation="Produits Éro",
        timezone_name="America/Toronto",
        opening_hours={"monday": [{"start": "09:00", "end": "18:00"}]},
        preferred_language="fr",
        greeting_message="Bonjour, bienvenue chez Produits Éro.",
        voice_api_key_hash="hash_a_12345678901234567890123456789012",
        voice_api_key_last4="keya",
        enabled=True,
        services=[
            {"name": "Cueillette en magasin", "duration_minutes": 15, "price": 0.0},
            {"name": "Conseil Snowboard en boutique", "duration_minutes": 30, "price": 0.0},
        ],
    )
    svc_a_pickup = CRMService(
        id=uuid4(),
        company_id=company_a.id,
        name="Cueillette en magasin",
        duration_minutes=15,
        price=0.0,
        currency="CAD",
        is_active=True,
        is_approved_by_owner=True,
        is_published=True,
    )
    svc_a_consult = CRMService(
        id=uuid4(),
        company_id=company_a.id,
        name="Conseil Snowboard en boutique",
        duration_minutes=30,
        price=0.0,
        currency="CAD",
        is_active=True,
        is_approved_by_owner=True,
        is_published=True,
    )
    from backend.app.models.commerce_connection import CommerceConnection
    conn_a = CommerceConnection(
        id=uuid4(),
        company_id=company_a.id,
        provider="shopify",
        external_account_id="produits-ero.myshopify.com",
        status="READY",
        display_name="Shopify Store",
    )
    session.add(conn_a)
    session.flush()

    # Products for A
    prod_a_snowboard = NormalizedCommerceRecord(
        id=uuid4(),
        company_id=company_a.id,
        connection_id=conn_a.id,
        provider="shopify",
        entity_type="product",
        source_record_id="sb-100",
        normalized_data={
            "product_id": "prod-sb-100",
            "product_name": "The 3p Fulfilled Snowboard",
            "unit_price": 749.95,
            "inventory_level": 8,
            "sku": "SB-3P-100",
            "in_stock": True,
            "product_category": "Snowboards",
        },
        source_updated_at=datetime.now(timezone.utc),
        deleted=False,
    )
    prod_a_powder = NormalizedCommerceRecord(
        id=uuid4(),
        company_id=company_a.id,
        connection_id=conn_a.id,
        provider="shopify",
        entity_type="product",
        source_record_id="sb-200",
        normalized_data={
            "product_id": "prod-sb-200",
            "product_name": "The Powder Cruiser Snowboard",
            "unit_price": 499.95,
            "inventory_level": 4,
            "sku": "SB-POW-200",
            "in_stock": True,
            "product_category": "Snowboards",
        },
        source_updated_at=datetime.now(timezone.utc),
        deleted=False,
    )
    prod_a_out_of_stock = NormalizedCommerceRecord(
        id=uuid4(),
        company_id=company_a.id,
        connection_id=conn_a.id,
        provider="shopify",
        entity_type="product",
        source_record_id="sb-999",
        normalized_data={
            "product_id": "prod-sb-999",
            "product_name": "Pro Alpine Competition Board",
            "unit_price": 899.95,
            "inventory_level": 0,
            "sku": "SB-ALP-999",
            "in_stock": False,
            "product_category": "Snowboards",
        },
        source_updated_at=datetime.now(timezone.utc),
        deleted=False,
    )
    session.add_all([
        member_a, mod_a_voice, mod_a_retail, mod_a_crm, config_a,
        svc_a_pickup, svc_a_consult, prod_a_snowboard, prod_a_powder, prod_a_out_of_stock,
    ])

    # 3. Tenant B: Non-retail Professional Services (Cabinet Juridique Lex)
    company_b = Company(
        id=uuid4(),
        name="Cabinet_Juridique_Lex",
        slug="cabinet-juridique-lex",
        email="contact@lex-avocats.example.com",
        country="CA",
        timezone="America/Montreal",
        industry="Services juridiques et contentieux",
        subscription_plan="professional",
        currency_code="CAD",
        website="https://lex-avocats.example.com",
        business_hours={
            "monday": [{"start": "09:00", "end": "17:00"}],
            "tuesday": [{"start": "09:00", "end": "17:00"}],
            "wednesday": [{"start": "09:00", "end": "17:00"}],
            "thursday": [{"start": "09:00", "end": "17:00"}],
            "friday": [{"start": "09:00", "end": "16:00"}],
            "saturday": [],
            "sunday": [],
        },
    )
    user_b = User(
        id=uuid4(),
        company_id=company_b.id,
        first_name="Maître",
        last_name="Lex",
        email="me.lex@lex-avocats.example.com",
        password_hash="fake-hash-b",
        role=UserRole.ADMIN,
        is_active=True,
    )
    session.add_all([company_b, user_b])
    session.flush()

    member_b = CompanyMembership(
        id=uuid4(),
        company_id=company_b.id,
        user_id=user_b.id,
        role="owner",
        is_active=True,
    )
    # Modules B: voice, crm, ocr (NO retail!)
    mod_b_voice = CompanyModule(company_id=company_b.id, module_id=modules[0].id, status=CompanyModuleStatus.ACTIVE, activated_at=now)
    mod_b_crm = CompanyModule(company_id=company_b.id, module_id=modules[2].id, status=CompanyModuleStatus.ACTIVE, activated_at=now)
    mod_b_ocr = CompanyModule(company_id=company_b.id, module_id=modules[3].id, status=CompanyModuleStatus.ACTIVE, activated_at=now)

    config_b = VoiceBusinessConfig(
        id=uuid4(),
        company_id=company_b.id,
        business_name="Cabinet Juridique Lex",
        voice_display_name="Cabinet Juridique Lex",
        custom_pronunciation="Cabinet Juridique Lex",
        timezone_name="America/Montreal",
        opening_hours={"monday": [{"start": "09:00", "end": "17:00"}]},
        preferred_language="fr",
        greeting_message="Bonjour, bienvenue au Cabinet Juridique Lex.",
        voice_api_key_hash="hash_b_12345678901234567890123456789012",
        voice_api_key_last4="keyb",
        enabled=True,
        services=[
            {"name": "Consultation juridique initiale", "duration_minutes": 60, "price": 250.0},
            {"name": "Révision de contrat commercial", "duration_minutes": 45, "price": 350.0},
        ],
    )
    svc_b_consult = CRMService(
        id=uuid4(),
        company_id=company_b.id,
        name="Consultation juridique initiale",
        duration_minutes=60,
        price=250.0,
        currency="CAD",
        is_active=True,
        is_approved_by_owner=True,
        is_published=True,
    )
    svc_b_contract = CRMService(
        id=uuid4(),
        company_id=company_b.id,
        name="Révision de contrat commercial",
        duration_minutes=45,
        price=350.0,
        currency="CAD",
        is_active=True,
        is_approved_by_owner=True,
        is_published=True,
    )
    doc_b_policy = TenantDocument(
        id=uuid4(),
        company_id=company_b.id,
        uploaded_by_user_id=user_b.id,
        filename="Conditions_Honoraires_et_Delais_Lex.pdf",
        kind="legal",
        sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        extracted_text="Les consultations juridiques sont facturées au taux horaire. Les avis écrits sont livrés sous un délai standard de 5 jours ouvrables. Paiement requis à la confirmation du mandat.",
        analysis_json=json.dumps({
            "summary": "Politique d'honoraires et délais de livraison des avis juridiques (5 jours ouvrables).",
            "document_type": "terms_and_conditions",
        }),
    )
    session.add_all([member_b, mod_b_voice, mod_b_crm, mod_b_ocr, config_b, svc_b_consult, svc_b_contract, doc_b_policy])

    session.commit()
    return session, company_a, user_a, prod_a_snowboard, prod_a_powder, prod_a_out_of_stock, company_b, user_b, doc_b_policy


def test_reserve_product_tool_in_store_pickup(tmp_path):
    """Vérifie le fonctionnement de ReserveProductTool pour la mise de côté en magasin."""
    session, company_a, user_a, prod_sb, prod_pow, prod_oos, _, _, _ = _create_test_db(tmp_path)
    tool = ReserveProductTool(session)
    tenant = TenantContext(company_id=company_a.id, user_id=user_a.id)
    ctx = ToolExecutionContext(
        tenant=tenant,
        user_id=user_a.id,
        permissions=frozenset({"ai:use", "data:read"}),
        request_id="req-test-reserve-1",
    )

    # 1. Non confirmé -> Doit demander la confirmation explicite
    args_unconfirmed = ReserveProductArgs(
        product_name_or_id="The 3p Fulfilled Snowboard",
        quantity=1,
        client_name="Jean Tremblay",
        pickup_date="2026-11-15",
        confirmed=False,
    )
    res_unconf = asyncio.run(tool.run(ctx, args_unconfirmed))
    assert res_unconf.success is False
    assert res_unconf.data.get("confirmation_required") is True
    assert res_unconf.data.get("product_name") == "The 3p Fulfilled Snowboard"
    assert res_unconf.data.get("unit_price") == 749.95

    # 2. Confirmé -> Doit générer la réservation sous code RES-...
    args_confirmed = ReserveProductArgs(
        product_name_or_id="The 3p Fulfilled Snowboard",
        quantity=1,
        client_name="Jean Tremblay",
        client_phone="+15145550199",
        pickup_date="2026-11-15",
        confirmed=True,
    )
    res_conf = asyncio.run(tool.run(ctx, args_confirmed))
    assert res_conf.success is True
    assert res_conf.data["status"] == "confirmed"
    assert res_conf.data["reference_code"].startswith("RES-")
    assert res_conf.data["reservation_type"] == "in_store_pickup_hold"
    # Doit explicitement indiquer que le stock distant n'est pas bloqué électroniquement
    assert res_conf.data["electronic_inventory_locked"] is False
    assert "Jean Tremblay" in res_conf.data["message"]
    assert "mise" in res_conf.data["message"] or "mis" in res_conf.data["message"]

    # 3. Produit en rupture de stock -> Doit refuser clairement
    args_oos = ReserveProductArgs(
        product_name_or_id="Pro Alpine Competition Board",
        quantity=1,
        client_name="Sophie Martin",
        confirmed=True,
    )
    res_oos = asyncio.run(tool.run(ctx, args_oos))
    assert res_oos.success is False
    assert "rupture de stock" in res_oos.error
    assert res_oos.data.get("state") == "OUT_OF_STOCK"

    # 4. Quantité excessive -> Doit refuser pour stock insuffisant
    args_excessive = ReserveProductArgs(
        product_name_or_id="The Powder Cruiser Snowboard",
        quantity=99,
        client_name="Pierre Gagnon",
        confirmed=True,
    )
    res_excessive = asyncio.run(tool.run(ctx, args_excessive))
    assert res_excessive.success is False
    assert "supérieure au stock disponible" in res_excessive.error
    assert res_excessive.data.get("state") == "INSUFFICIENT_STOCK"


def test_universal_multi_tenant_discovery_and_source_precedence(tmp_path):
    """Vérifie la découverte dynamique à l'exécution pour Tenant A (Retail) vs Tenant B (Juridique)."""
    session, company_a, user_a, _, _, _, company_b, user_b, doc_b = _create_test_db(tmp_path)
    intel = CompanyIntelligenceService(session)

    # 1. Profil dynamique Tenant A (Retail)
    profile_a = intel.get_profile(company_a.id)
    assert profile_a.has_retail_commerce is True
    assert profile_a.has_crm_booking is True
    assert len(profile_a.public_products) >= 2
    assert "catalog.search" in profile_a.source_capabilities
    assert "inventory.read" in profile_a.source_capabilities
    assert "reservations.in_store_pickup" in profile_a.source_capabilities

    # 2. Profil dynamique Tenant B (Juridique / Non-retail)
    profile_b = intel.get_profile(company_b.id)
    assert profile_b.has_retail_commerce is False  # Aucun retail
    assert profile_b.has_crm_booking is True  # Consultations CRM
    assert len(profile_b.public_products) == 0  # 0 produits
    assert profile_b.has_public_documents is True  # Documents de politiques présents
    assert len(profile_b.public_documents) == 1
    assert "documents.search" in profile_b.source_capabilities
    assert "catalog.search" not in profile_b.source_capabilities

    # 3. SourcePrecedenceService
    assert SourcePrecedenceService.precedence_order(SourcePrecedenceCategory.INVENTORY)[0] == "live_connector"
    assert SourcePrecedenceService.precedence_order(SourcePrecedenceCategory.SERVICES)[0] == "crm_service_catalog"
    assert SourcePrecedenceService.precedence_order(SourcePrecedenceCategory.POLICIES)[0] == "tenant_document_rag"

    pref_inv = SourcePrecedenceService.resolve_preferred_source(
        SourcePrecedenceCategory.INVENTORY,
        ["historical_csv", "live_connector"],
    )
    assert pref_inv == "live_connector"

    assert SourcePrecedenceService.freshness_for_source("shopify_live") == SourceFreshnessStatus.LIVE
    assert SourcePrecedenceService.freshness_for_source("historical_csv") == SourceFreshnessStatus.HISTORICAL_IMPORT


def test_public_voice_caller_security_boundary(tmp_path):
    """Vérifie que l'appelant public ne peut exécuter QUE les outils autorisés de son tenant."""
    session, company_a, user_a, _, _, _, company_b, user_b, _ = _create_test_db(tmp_path)

    # Permissions d'un appelant public entrant non-authentifié
    public_perms = PUBLIC_VOICE_CALLER_PERMISSIONS
    assert is_public_voice_caller(public_perms) is True

    # --- TENANT A (Retail actif, CRM actif) ---
    assert public_voice_tool_allowed("get_business_info", has_crm_booking=True, has_retail_commerce=True) is True
    assert public_voice_tool_allowed("check_availability", has_crm_booking=True, has_retail_commerce=True) is True
    assert public_voice_tool_allowed("create_appointment", has_crm_booking=True, has_retail_commerce=True) is True
    assert public_voice_tool_allowed("get_product_detail", has_crm_booking=True, has_retail_commerce=True) is True
    assert public_voice_tool_allowed("reserve_product", has_crm_booking=True, has_retail_commerce=True) is True
    # Outils privés jamais autorisés en public
    assert public_voice_tool_allowed("get_sales_summary", has_crm_booking=True, has_retail_commerce=True) is False
    assert public_voice_tool_allowed("get_unpaid_invoices", has_crm_booking=True, has_retail_commerce=True) is False
    assert public_voice_tool_allowed("get_profit_margin", has_crm_booking=True, has_retail_commerce=True) is False

    # --- TENANT B (Juridique: CRM actif, Documents actifs, Retail INACTIF) ---
    assert public_voice_tool_allowed("get_business_info", has_crm_booking=True, has_retail_commerce=False, has_documents=True) is True
    assert public_voice_tool_allowed("check_availability", has_crm_booking=True, has_retail_commerce=False, has_documents=True) is True
    assert public_voice_tool_allowed("create_appointment", has_crm_booking=True, has_retail_commerce=False, has_documents=True) is True
    assert public_voice_tool_allowed("search_documents", has_crm_booking=True, has_retail_commerce=False, has_documents=True) is True
    # Retail strictement INTERDIT pour Tenant B
    assert public_voice_tool_allowed("get_product_detail", has_crm_booking=True, has_retail_commerce=False, has_documents=True) is False
    assert public_voice_tool_allowed("reserve_product", has_crm_booking=True, has_retail_commerce=False, has_documents=True) is False


def test_tool_authorization_policy_enforcement(tmp_path):
    """Vérifie le rejet de frontière par ToolAuthorizationPolicy pour un appelant public."""
    session, company_a, user_a, _, _, _, company_b, user_b, _ = _create_test_db(tmp_path)
    policy = ToolAuthorizationPolicy(session, AssistantRegistry())

    # Contexte appelant public sur Tenant B (non-retail)
    tenant_b = TenantContext(company_id=company_b.id, user_id=user_b.id)
    public_ctx_b = ToolExecutionContext(
        tenant=tenant_b,
        user_id=user_b.id,
        permissions=PUBLIC_VOICE_CALLER_PERMISSIONS,
        request_id="req-test-auth-1",
        voice_path=True,
    )

    reserve_tool = ReserveProductTool(session)
    sales_tool = GetSalesSummaryTool(session, None)

    # 1. Tentative d'utiliser ReserveProductTool sur Tenant B (non-retail) -> Doit lever ToolAuthorizationError
    with pytest.raises(ToolAuthorizationError, match="Caller authentication is required"):
        policy.authorize(reserve_tool, public_ctx_b)

    # 2. Tentative d'utiliser GetSalesSummaryTool (données financières privées) -> Doit lever ToolAuthorizationError
    with pytest.raises(ToolAuthorizationError, match="Caller authentication is required"):
        policy.authorize(sales_tool, public_ctx_b)


def test_chat_service_universal_system_instruction_neutrality():
    """Vérifie que les instructions système sont universelles et ne présument d'aucun domaine spécifique."""
    prompt = _localized_system_instruction(
        SYSTEM_INSTRUCTION,
        user_language="fr-CA",
        company_country="CA",
        company_currency="CAD",
        company_timezone="America/Toronto",
        is_voice_call=True,
    )

    # 1. Vérification de la classification stricte des intentions
    assert "FOUR-WAY INTENTION CLASSIFICATION" in prompt
    assert "Appointment / Service Booking" in prompt
    assert "In-Store Product Reservation" in prompt
    assert "reserve_product" in prompt
    assert "Commercial Order" in prompt
    assert "Informational Inquiry" in prompt

    # 2. Vérification des questions ouvertes
    assert "Quel est votre produit le moins cher ?" in prompt
    assert "Peux-tu comparer le produit A et le produit B ?" in prompt

    # 3. Vérification des dates relatives et politiques
    assert "Resolve relative dates ('lundi prochain', 'mercredi matin', 'demain')" in prompt
    assert "Business Policies, Delivery Delays & Document Knowledge" in prompt
    assert "Current date and time:" in prompt

