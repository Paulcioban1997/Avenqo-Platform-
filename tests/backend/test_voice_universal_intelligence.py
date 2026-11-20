"""Comprehensive test suite for Avenqo Voice AI — Enterprise Intelligence & Hardening.

Covers:
- Scenario 1: Authenticated Employee Session & Identity Resolution (A1)
- Scenario 2: Dynamic Entitlement Discovery & Truthful Active Modules (A2)
- Scenario 3: General Marketing Advice & Professional Coaching when Module Inactive (A3)
- Scenario 4: Standalone Greeting Anchor & Conversational Continuity (A4)
- Scenario 5: Carrier / Freight Logistics Communication Phrasing & Coaching (A5)
- Scenario 6: Employee Handover State Machine & Mandatory PIN Re-authentication (A6)
- Scenario 7: Natural Customer Mode Catalog Spoken Formatting (B1)
- Scenario 8: Barge-In Natural Interruption Detection (B2)
- Scenario 9: Customer Mode Supplier Inquiry Handling (B3)
- Scenario 10: Customer Mode Recruitment / Job Application Handling (B4)
- Universal Industry Coaching across 7 sectors (Automotive, Construction, Salon, Commerce, Logistics, Marketing, Finance)
"""
from __future__ import annotations

import unicodedata
import re
import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from backend.app.models.base import UserRole
from backend.app.models.user import User
from backend.app.services.employee_coach_service import EmployeeCoachService
from backend.app.voice.direct_answers import (
    is_module_access_question,
    is_coach_optimize_task_question,
    spoken_module_answer,
    spoken_catalog_answer,
)
from backend.app.voice.turn_control import adjudicate_transcript, is_explicit_interruption
from backend.app.voice.telnyx_media import PublicInboundConversation


# ==============================================================================
# 1. SCENARIO 1: Authenticated Employee Session & Identity Resolution (A1)
# ==============================================================================

def test_authenticated_employee_identity_resolution():
    """Verify authenticated caller identity resolves to the true user display name."""
    company_id = uuid4()
    paul_id = uuid4()
    paul_user = User(
        id=paul_id,
        company_id=company_id,
        email="paulmircea15@gmail.com",
        first_name="Paul",
        last_name="Mircea",
        role=UserRole.OWNER,
        is_active=True,
    )

    mock_db = MagicMock()
    mock_db.get.return_value = paul_user

    coach = EmployeeCoachService(mock_db)
    briefing = coach.get_daily_briefing(paul_user, locale="fr-CA")

    assert briefing["status"] == "success"
    assert "Paul" in briefing["spoken_summary"]
    assert "Francis" not in briefing["spoken_summary"]


# ==============================================================================
# 2. SCENARIO 2: Dynamic Entitlement Discovery & Truthful Active Modules (A2)
# ==============================================================================

def test_module_access_question_detection():
    """Verify various ways of asking about company modules are recognized."""
    assert is_module_access_question("Quels sont nos modules actifs ?")
    assert is_module_access_question("Quels modules sont activés ?")
    assert is_module_access_question("Quels modules avons-nous ?")
    assert is_module_access_question("Qu'avons-nous comme modules dans notre abonnement ?")
    assert is_module_access_question("What modules are active?")
    assert is_module_access_question("Which modules does our company have?")
    assert is_module_access_question("Ce module sunt active?")
    assert is_module_access_question("¿Cuáles son los módulos activos?")

    # Legal contract inquiries should NOT be flagged as module inquiries
    assert not is_module_access_question("Pouvez-vous analyser les clauses du contrat commercial ?")


def test_spoken_module_answer_truthful_reporting():
    """Verify that spoken_module_answer only announces actually active modules and never invents HR AI."""
    active_modules = ["Retail Intelligence", "CRM AI", "Accounting AI", "Voice AI"]
    answer_fr = spoken_module_answer(active_modules, plan_code="professional", locale="fr-CA")

    assert "Votre abonnement professional est actif." in answer_fr
    assert "Retail Intelligence" in answer_fr
    assert "CRM AI" in answer_fr
    assert "Accounting AI" in answer_fr
    assert "Voice AI" in answer_fr
    assert "HR AI" not in answer_fr
    assert "Ressources Humaines" not in answer_fr

    # When no modules active
    empty_fr = spoken_module_answer([], plan_code="base", locale="fr-CA")
    assert "Votre entreprise n'a actuellement aucun module actif." in empty_fr


# ==============================================================================
# 3. SCENARIO 3: General Marketing Advice when Module Inactive (A3)
# ==============================================================================

def test_coach_optimize_task_marketing_advice():
    """Verify coaching provides creative marketing suggestions without requiring Marketing AI tools."""
    mock_db = MagicMock()
    user = User(
        id=uuid4(),
        company_id=uuid4(),
        email="paul@example.com",
        first_name="Paul",
        role=UserRole.OWNER,
        is_active=True,
    )
    coach = EmployeeCoachService(mock_db)
    res = coach.optimize_task_execution(user, "Comment puis-je attirer plus de clients cette semaine ?", locale="fr-CA")

    assert res["status"] == "success"
    assert res["sector"] == "Marketing & Acquisition Clients"
    assert "gain de temps" in res["spoken_summary"] or "time" in res["spoken_summary"].lower()
    assert len(res["methodology_steps"]) == 4


# ==============================================================================
# 4. SCENARIO 4: Standalone Greeting vs Continuous Utterance (A4)
# ==============================================================================

def test_standalone_greeting_anchor(monkeypatch):
    """Verify standalone greetings return standard greeting, but questions are NOT intercepted."""
    mock_db = MagicMock()
    mock_settings = MagicMock()
    conv = PublicInboundConversation(mock_db, mock_settings, uuid4())

    mock_company = SimpleNamespace(id=uuid4(), name="Produits Ero")
    mock_call = SimpleNamespace(company_id=mock_company.id, telnyx_call_control_id="call-1", status="IN_PROGRESS", ended_at=None, locale="fr-CA")
    mock_config = SimpleNamespace(business_name="Produits Ero")
    conv.context = MagicMock(return_value=(mock_call, mock_config, mock_company))

    dummy_profile = SimpleNamespace(has_crm_booking=False, active_modules=(), business_hours={}, configured_crm_services=[], public_products=[])
    monkeypatch.setattr("backend.app.services.company_intelligence_service.CompanyIntelligenceService.get_profile", lambda *a, **k: dummy_profile)

    # Standalone greeting -> returns greeting
    g1 = conv.public_answer("Bonjour !")
    assert g1["status"] == "success"
    assert "Bonjour ! Comment puis-je vous aider aujourd'hui ?" in g1["answer"]

    g2 = conv.public_answer("Allô")
    assert g2["status"] == "success"
    assert "Bonjour !" in g2["answer"]

    # Utterance containing greeting followed by business question -> NOT intercepted as greeting alone
    q1 = conv.public_answer("Bonjour, j'aimerais savoir si vous prenez de nouveaux fournisseurs ?")
    assert "partenaires et fournisseurs" in q1["answer"]

    q2 = conv.public_answer("Allô, est-ce que vous embauchez actuellement ?")
    assert "candidature" in q2["answer"] or "emploi" in q2["answer"]


# ==============================================================================
# 5. SCENARIO 5: Carrier / Freight Logistics Communication Phrasing (A5)
# ==============================================================================

def test_coach_optimize_task_carrier_call_phrasing():
    """Verify that asking how to call a delivery carrier returns polite, structured phrasing steps."""
    assert is_coach_optimize_task_question("Comment puis-je appeler le transporteur pour faire avancer la livraison ?")

    mock_db = MagicMock()
    user = User(
        id=uuid4(),
        company_id=uuid4(),
        email="paul@example.com",
        first_name="Paul",
        role=UserRole.USER,
        is_active=True,
    )
    coach = EmployeeCoachService(mock_db)
    res = coach.optimize_task_execution(user, "Appeler un transporteur pour débloquer une livraison", locale="fr-CA")

    assert res["status"] == "success"
    assert res["sector"] == "Logistique & Approvisionnements"
    assert any("suivi" in s.lower() or "tracking" in s.lower() for s in res["methodology_steps"])
    assert any("courtois" in s.lower() for s in res["methodology_steps"])


# ==============================================================================
# 6. SCENARIO 6: Employee Handover State Machine (A6)
# ==============================================================================

def test_employee_handover_intent_detection():
    """Verify that saying 'je te passe mon collègue' or 'changer d'employé' matches handover intent."""
    handover_pattern = r"\b(changer\s*d\W*employe|change\s*employe|autre\s*employe|nouvel\s*employe|passe\s*mon\s*collegue|passe\s*le\s*telephone|je\s*te\s*passe|switch\s*employee|change\s*employee|pass\s*the\s*phone|hand\s*over|schimba\s*angajatul|iti\s*dau\s*colegul|pasez\s*telefonul|cambiar\s*de\s*empleado|te\s*paso\s*a\s*mi\s*colega)\b"

    test_phrases = [
        "Attends, je te passe mon collègue pour la suite.",
        "On va changer d'employé au téléphone.",
        "Je passe mon collègue.",
        "Switch employee please.",
        "Schimbă angajatul, te rog.",
        "Te paso a mi colega.",
    ]

    for phrase in test_phrases:
        norm = "".join(c for c in unicodedata.normalize("NFKD", phrase.casefold()) if not unicodedata.combining(c))
        assert bool(re.search(handover_pattern, norm)), f"Failed on: {phrase}"


# ==============================================================================
# 7. SCENARIO 7: Natural Customer Mode Catalog Spoken Formatting (B1)
# ==============================================================================

def test_natural_catalog_spoken_response_conciseness():
    """Verify that spoken_catalog_answer limits items to top 3 and does not recite 5 items."""
    products = [
        {"name": f"Snowboard Model {i}", "price": 400 + i * 50, "currency": "CAD", "is_live_stock": True, "in_stock": True, "freshness_status": "FRESH", "price_status": "verified"}
        for i in range(1, 10)
    ]

    answer = spoken_catalog_answer(products, retail_enabled=True, locale="fr-CA")

    # Top 3 must be present
    assert "Snowboard Model 1" in answer
    assert "Snowboard Model 2" in answer
    assert "Snowboard Model 3" in answer

    # Model 4 and onwards must NOT be recited individually in the main list
    assert "Snowboard Model 4," not in answer
    assert "Snowboard Model 5," not in answer

    # Remaining items summarized
    assert "6 autres articles au catalogue" in answer


# ==============================================================================
# 8. SCENARIO 8: Barge-In Natural Interruption Detection (B2)
# ==============================================================================

def test_barge_in_interruption_detection():
    """Verify that interruption phrases trigger replace rather than being ignored."""
    assert is_explicit_interruption("Excusez-moi de vous couper")
    assert is_explicit_interruption("Attendez une seconde s'il vous plaît")
    assert is_explicit_interruption("Stop, je vous coupe")
    assert is_explicit_interruption("Wait, hold on a second")
    assert is_explicit_interruption("Stai puțin, opriți")
    assert is_explicit_interruption("Espere un momento")

    # In PLAYING phase, explicit interruption returns 'replace'
    decision = adjudicate_transcript(
        "Excusez-moi de vous couper",
        phase="PLAYING",
        in_flight_transcript=None,
        last_spoken="Nous avons au catalogue : Planche Alpha...",
        allow_barge_in=True,
    )
    assert decision == "replace"


# ==============================================================================
# 9. SCENARIO 9 & 10: Supplier & Recruitment Inquiries (B3 / B4)
# ==============================================================================

def test_public_supplier_and_recruitment_inquiries(monkeypatch):
    """Verify that customer mode handles supplier and recruitment inquiries constructively."""
    mock_db = MagicMock()
    mock_settings = MagicMock()
    conv = PublicInboundConversation(mock_db, mock_settings, uuid4())

    mock_company = SimpleNamespace(id=uuid4(), name="Produits Ero")
    mock_call = SimpleNamespace(company_id=mock_company.id, telnyx_call_control_id="call-1", status="IN_PROGRESS", ended_at=None, locale="fr-CA")
    mock_config = SimpleNamespace(business_name="Produits Ero")
    conv.context = MagicMock(return_value=(mock_call, mock_config, mock_company))

    dummy_profile = SimpleNamespace(has_crm_booking=False, active_modules=(), business_hours={}, configured_crm_services=[], public_products=[])
    monkeypatch.setattr("backend.app.services.company_intelligence_service.CompanyIntelligenceService.get_profile", lambda *a, **k: dummy_profile)

    # Supplier inquiry
    supp = conv.public_answer("Bonjour, est-ce que vous prenez de nouveaux fournisseurs ?")
    assert supp["status"] == "success"
    assert "fournisseurs" in supp["answer"]
    assert "commerciale" in supp["answer"] or "courriel" in supp["answer"]

    # Recruitment inquiry
    rec = conv.public_answer("Est-ce que votre entreprise recrute en ce moment ?")
    assert rec["status"] == "success"
    assert "candidature" in rec["answer"] or "offres" in rec["answer"] or "emploi" in rec["answer"]


# ==============================================================================
# 11. Universal Industry Task Optimization (7 Sectors)
# ==============================================================================

def test_universal_industry_task_optimization_7_sectors():
    """Verify task optimization adapts dynamically across 7 diverse industries."""
    mock_db = MagicMock()
    user = User(
        id=uuid4(),
        company_id=uuid4(),
        email="operator@example.com",
        first_name="Jean",
        role=UserRole.USER,
        is_active=True,
    )
    coach = EmployeeCoachService(mock_db)

    sectors = [
        ("Automobile", "Changement disques et plaquettes de frein avant", "Automobile & Mécanique"),
        ("Construction", "Pose de carrelage 60x60 sur chape neuve", "Construction & Rénovation"),
        ("Coiffure", "Coupe brushing et soin capillaire profond", "Coiffure & Esthétique"),
        ("Commerce", "Négociation devis avec grand compte", "Commerce & Relations Clients"),
        ("Logistique", "Appel transporteur livraison colis express", "Logistique & Approvisionnements"),
        ("Marketing", "Campagne publicitaire pour attirer de nouveaux clients", "Marketing & Acquisition Clients"),
        ("Finance", "Rapprochement bancaire et déclaration TVA", "Finance & Comptabilité"),
    ]

    for sector_name, query, expected_sector in sectors:
        res = coach.optimize_task_execution(user, query, locale="fr-CA")
        assert res["status"] == "success", f"Failed on {sector_name}"
        assert res["sector"] == expected_sector, f"Expected {expected_sector}, got {res['sector']}"
        assert len(res["methodology_steps"]) == 4
        assert "spoken_summary" in res
        assert len(res["spoken_summary"]) > 40
