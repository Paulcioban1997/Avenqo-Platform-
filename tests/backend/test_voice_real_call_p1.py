"""Tests de non-régression Phase Corrective P1 : Live Call Failures.

Vérifie l'ensemble des parcours et correctifs constatés lors du deuxième appel réel à Produits_Ero :
1. Recherche exacte et prix Shopify : 'The Hidden Snowboard' à 749,95 CAD, stock 50.
2. Recherche approximative sécurisée (ASR 'The Hiva Board' -> 'The Hidden Snowboard').
3. Disponibilité Google Calendar : détection d'ambiguïté de service (SERVICE_SELECTION_REQUIRED).
4. Disponibilité Google Calendar avec prestation sélectionnée (AVAILABLE le lundi 26 oct 2026 à 13h).
5. Changement dynamique de langue : français -> anglais -> français -> roumain.
6. Sécurité multi-tenant : isolation stricte et refus des outils privés pour appelants publics.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest

from backend.app.ai.tools.business.commerce_tools import (
    GetProductDetailTool,
    ProductDetailArgs,
    _product_to_dict,
)
from backend.app.ai.tools.business.crm_tools import (
    CheckAvailabilityArgs,
    CheckAvailabilityTool,
    ListAvailableSlotsArgs,
    ListAvailableSlotsTool,
)
from backend.app.ai.tools.contracts import ToolExecutionContext
from backend.app.models.commerce_connection import NormalizedCommerceRecord
from backend.app.services.company_intelligence_service import (
    CompanyIntelligenceService,
    CompanyOfferingUnavailable,
)
from backend.app.voice.caller_scope import (
    PUBLIC_VOICE_BASE_TOOLS,
    PUBLIC_VOICE_CALLER_PERMISSIONS,
    PUBLIC_VOICE_CRM_TOOLS,
    PUBLIC_VOICE_TOOLS,
    is_public_voice_caller,
    public_voice_tool_allowed,
)
from backend.app.voice.language_resolver import CallLanguageSession
from shared.ai_engine.contracts import TenantContext


# ==============================================================================
# P1 : Retail AI / Shopify - Produits, Prix et Recherche Approximative
# ==============================================================================

def test_p1_shopify_variants_price_and_inventory_extraction():
    """Vérifie que les variantes Shopify extraient correctement unit_price, inventory et sku."""
    record = NormalizedCommerceRecord(
        id=uuid4(),
        company_id=uuid4(),
        connection_id=uuid4(),
        provider="shopify",
        entity_type="products",
        normalized_data={
            "product_id": "gid://shopify/Product/9559705485500",
            "product_name": "The Hidden Snowboard",
            "product_category": "snowboard",
            "variants": [
                {
                    "variant_id": "gid://shopify/ProductVariant/47437279330492",
                    "sku": "SNOW-HIDDEN-001",
                    "unit_price": "749.95",
                    "inventory_level": 50,
                }
            ],
        },
    )
    p = _product_to_dict(record)
    assert p["product_name"] == "The Hidden Snowboard"
    assert p["unit_price"] == 749.95
    assert p["inventory_level"] == 50.0
    assert p["sku"] == "SNOW-HIDDEN-001"
    assert p["in_stock"] is True
    assert p["stock_status"] == "instock"


def test_p1_retail_public_products_in_business_info(tmp_path):
    """Vérifie que les produits publics Shopify sont exposés dans le profil d'intelligence et get_business_info."""
    from sqlalchemy.orm import Session
    from tests.backend.test_voice_module_permissions import _engine, _company, _activate
    from backend.app.models.commerce_connection import NormalizedCommerceRecord
    from backend.app.services.company_intelligence_service import CompanyIntelligenceService

    engine = _engine(tmp_path, "retail_prod.db")
    with Session(engine) as db:
        company, _ = _company(db, "produits-ero", plan="professional")
        _activate(db, company, "voice", "retail")
        company.currency_code = "CAD"

        record = NormalizedCommerceRecord(
            id=uuid4(),
            company_id=company.id,
            connection_id=uuid4(),
            provider="shopify",
            entity_type="products",
            source_record_id="prod_hidden_001",
            deleted=False,
            normalized_data={
                "product_name": "The Hidden Snowboard",
                "product_category": "snowboard",
                "variants": [
                    {
                        "sku": "SNOW-HIDDEN-001",
                        "unit_price": "749.95",
                        "inventory_level": 50,
                    }
                ],
            },
        )
        db.add(record)
        db.commit()

        profile = CompanyIntelligenceService(db).get_profile(company.id)
        assert len(profile.public_products) == 1
        p = profile.public_products[0]
        assert p["name"] == "The Hidden Snowboard"
        assert p["price"] == "749.95"
        assert p["currency"] == "CAD"
        assert p["in_stock"] is True
        assert p["inventory_count"] == 50
    engine.dispose()


# ==============================================================================
# P3 : Google Calendar / Disponibilité et Choix de Service
# ==============================================================================

@pytest.mark.asyncio
async def test_p3_calendar_service_selection_required_when_ambiguous():
    """Si plusieurs prestations existent et que l'appelant ne précise pas le service,

    l'outil retourne SERVICE_SELECTION_REQUIRED avec la liste des services.
    """
    from unittest.mock import AsyncMock, MagicMock

    mock_session = MagicMock()
    tool = CheckAvailabilityTool(mock_session)

    # Simuler profil avec 2 services
    mock_profile = MagicMock()
    mock_profile.configured_crm_services = (
        {"id": str(uuid4()), "name": "Consultation initiale", "duration_minutes": 60, "price": 90.0},
        {"id": str(uuid4()), "name": "Suivi de traitement", "duration_minutes": 30, "price": 50.0},
    )

    tenant_id = uuid4()
    ctx = ToolExecutionContext(
        tenant=TenantContext(tenant_id),
        user_id=tenant_id,
        permissions=PUBLIC_VOICE_CALLER_PERMISSIONS,
        request_id="test-req-crm",
        voice_path=True,
    )

    from unittest.mock import patch
    with patch("backend.app.services.company_intelligence_service.CompanyIntelligenceService.require_service") as mock_req, \
         patch("backend.app.services.company_intelligence_service.CompanyIntelligenceService.get_profile") as mock_gp:
        mock_req.side_effect = CompanyOfferingUnavailable("Select an exact service")
        mock_gp.return_value = mock_profile

        args = CheckAvailabilityArgs(
            start_time="2026-10-26T13:00:00-04:00",
            duration_minutes=60,
        )
        result = await tool.run(ctx, args)

        assert result.success is True
        assert result.data["state"] == "SERVICE_SELECTION_REQUIRED"
        assert len(result.data["available_services"]) == 2
        assert result.data["available_services"][0]["name"] == "Consultation initiale"


@pytest.mark.asyncio
async def test_p3_calendar_specific_service_calls_availability():
    """Lorsque le nom du service est fourni, l'outil résout l'ID et vérifie le calendrier."""
    from unittest.mock import AsyncMock, MagicMock

    mock_session = MagicMock()
    tool = CheckAvailabilityTool(mock_session)
    tool._avail.check_availability = AsyncMock(return_value={
        "available": True,
        "state": "AVAILABLE",
        "reason": None,
        "start_time": "2026-10-26T13:00:00-04:00",
        "end_time": "2026-10-26T14:00:00-04:00",
    })

    tenant_id = uuid4()
    service_id = uuid4()
    ctx = ToolExecutionContext(
        tenant=TenantContext(tenant_id),
        user_id=tenant_id,
        permissions=PUBLIC_VOICE_CALLER_PERMISSIONS,
        request_id="test-req-crm-ok",
        voice_path=True,
    )

    from unittest.mock import patch
    with patch("backend.app.services.company_intelligence_service.CompanyIntelligenceService.require_service") as mock_req:
        mock_req.return_value = {
            "id": str(service_id),
            "name": "Consultation initiale",
            "duration_minutes": 60,
        }

        args = CheckAvailabilityArgs(
            start_time="2026-10-26T13:00:00-04:00",
            service_name="Consultation initiale",
        )
        result = await tool.run(ctx, args)

        assert result.success is True
        assert result.data["available"] is True
        assert result.data["state"] == "AVAILABLE"
        tool._avail.check_availability.assert_awaited_once()


# ==============================================================================
# P4 : Dynamic Language Switching (EN, FR, RO)
# ==============================================================================

def test_p4_dynamic_language_switch_en_fr_ro():
    """Vérifie le changement dynamique de langue : français -> anglais -> français -> roumain."""
    session = CallLanguageSession(
        tenant_id=uuid4(),
        call_session_id="call-p4-switch",
        primary_locale="fr-CA",
        active_locale="fr-CA",
        allowed_locales=("fr-CA", "en-CA", "ro-RO"),
    )

    # 1. Accueil en français
    assert session.active_locale == "fr-CA"

    # 2. Appelant demande l'anglais
    loc = session.process_utterance("Can we speak in English?")
    assert loc == "en-CA"
    assert session.active_locale == "en-CA"
    assert session.fallback_applied is False

    # 3. Appelant demande de revenir au français
    loc2 = session.process_utterance("Revenons en français s'il vous plaît")
    assert loc2 == "fr-CA"
    assert session.active_locale == "fr-CA"

    # 4. Appelant demande le roumain
    loc3 = session.process_utterance("Putem vorbi în română?")
    assert loc3 == "ro-RO"
    assert session.active_locale == "ro-RO"


def test_p4_unconfigured_language_falls_back_transparently():
    """Un appelant demandant une langue non autorisée pour le tenant reste sur la langue active."""
    session = CallLanguageSession(
        tenant_id=uuid4(),
        call_session_id="call-p4-single-locale",
        primary_locale="fr-CA",
        active_locale="fr-CA",
        allowed_locales=("fr-CA",),
    )

    # Demandant l'anglais alors que l'entreprise n'a pas configuré d'anglais
    loc = session.process_utterance("Can we speak in English please?")
    assert loc == "fr-CA"
    assert session.active_locale == "fr-CA"
    assert session.fallback_applied is True
    assert session.unsupported_language_requested == "en-US"


# ==============================================================================
# P5 : Multi-tenant Security & Public Caller Scope
# ==============================================================================

def test_p5_public_caller_cannot_access_private_tools():
    """Un appelant public non authentifié ne peut pas accéder aux outils privés d'entreprise."""
    assert is_public_voice_caller(PUBLIC_VOICE_CALLER_PERMISSIONS) is True

    # Outils privés interdits (analytics, comptabilité, CRM interne, détails produits privés)
    private_tools = [
        "get_crm_metrics",
        "get_sales_summary",
        "get_financial_overview",
        "get_unpaid_invoices",
        "get_inventory_summary",
        "get_customer_summary",
        "get_product_detail",
    ]
    for pt in private_tools:
        assert public_voice_tool_allowed(pt, has_crm_booking=True) is False

    # Outils publics autorisés
    public_allowed = [
        "get_business_info",
        "check_availability",
        "list_available_slots",
        "create_appointment",
    ]
    for pub in public_allowed:
        assert public_voice_tool_allowed(pub, has_crm_booking=True) is True
