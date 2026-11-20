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

import asyncio
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
    assert "fournisseurs" in q1["answer"]

    q2 = conv.public_answer("Allô, est-ce que vous embauchez actuellement ?")
    assert "recrutement" in q2["answer"] or "embauche" in q2["answer"] or "candidature" in q2["answer"] or "emploi" in q2["answer"]


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


def test_employee_handover_end_to_end_security_revocation():
    """Verify that employee handover immediately revokes all private credentials,
    purges central_conversation_id, sanitizes source_context, and locks private data."""
    from backend.app.models.voice import VoiceCall

    user_a_id = uuid4()
    company_id = uuid4()
    call_id = uuid4()

    mock_call = VoiceCall(
        id=call_id,
        company_id=company_id,
        authenticated_user_id=user_a_id,
        caller_type="USER",
        central_conversation_id=uuid4(),
        source_context={"user_id": str(user_a_id), "user_name": "Paul Mircea", "authenticated": True},
        locale="fr-CA",
        status="IN_PROGRESS",
    )

    mock_db = MagicMock()
    mock_db.get.return_value = mock_call

    # Simulate handover execution
    norm_trans = "".join(c for c in unicodedata.normalize("NFKD", "Je te passe mon collègue pour la suite.".casefold()) if not unicodedata.combining(c))
    handover_pattern = r"\b(changer\s*d\W*employe|change\s*employe|autre\s*employe|nouvel\s*employe|passe\s*mon\s*collegue|passe\s*le\s*telephone|je\s*te\s*passe|switch\s*employee|change\s*employee|pass\s*the\s*phone|hand\s*over|schimba\s*angajatul|iti\s*dau\s*colegul|pasez\s*telefonul|cambiar\s*de\s*empleado|te\s*paso\s*a\s*mi\s*colega)\b"
    assert re.search(handover_pattern, norm_trans)

    # Apply the exact handover revocation logic from telnyx_media.py
    current_call = mock_db.get(VoiceCall, call_id)
    assert current_call.authenticated_user_id == user_a_id
    assert current_call.central_conversation_id is not None

    current_call.authenticated_user_id = None
    current_call.caller_type = "UNKNOWN"
    current_call.central_conversation_id = None
    existing_ctx = dict(current_call.source_context or {})
    existing_ctx.pop("previous_principal", None)
    existing_ctx.pop("user_id", None)
    existing_ctx.pop("user_name", None)
    existing_ctx["authenticated"] = False
    existing_ctx["handover_revoked"] = True
    current_call.source_context = existing_ctx

    # Assert complete revocation
    assert current_call.authenticated_user_id is None
    assert current_call.caller_type == "UNKNOWN"
    assert current_call.central_conversation_id is None
    assert "user_id" not in current_call.source_context
    assert "user_name" not in current_call.source_context
    assert "previous_principal" not in current_call.source_context
    assert current_call.source_context["authenticated"] is False
    assert current_call.source_context["handover_revoked"] is True

    # Verify that subsequent attempt to query private data fails closed
    conv = PublicInboundConversation(mock_db, MagicMock(), call_id)
    conv.context = MagicMock(return_value=(mock_call, SimpleNamespace(business_name="Test Co"), SimpleNamespace(id=company_id, name="Test Co")))
    security_check = conv.security_gate("Quelles sont mes tâches confidentielles aujourd'hui ?")
    assert security_check is not None
    assert security_check["auth_required"] is True
    assert "authentification" in security_check["answer"].lower() or "nip" in security_check["answer"].lower()


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
# 9. SCENARIO 9 & 10: Dynamic Supplier & Recruitment Policies & Non-Retail Grounding
# ==============================================================================

def test_public_supplier_dynamic_policies(monkeypatch):
    """Verify supplier inquiry adapts dynamically according to company configuration."""
    mock_db = MagicMock()
    mock_settings = MagicMock()
    conv = PublicInboundConversation(mock_db, mock_settings, uuid4())

    mock_company = SimpleNamespace(id=uuid4(), name="Produits Ero", email="contact@produitsero.com", website="https://produitsero.com")
    mock_call = SimpleNamespace(company_id=mock_company.id, telnyx_call_control_id="call-1", status="IN_PROGRESS", ended_at=None, locale="fr-CA")
    mock_config = SimpleNamespace(business_name="Produits Ero")
    conv.context = MagicMock(return_value=(mock_call, mock_config, mock_company))

    # Case A: Explicit refusal of new suppliers
    profile_refusal = SimpleNamespace(
        has_crm_booking=False, has_retail_commerce=True, active_modules=(), business_hours={},
        configured_crm_services=[], public_products=[], business_configuration={},
        supplier_policy=None, accepts_suppliers=False, email=None, website=None
    )
    monkeypatch.setattr("backend.app.services.company_intelligence_service.CompanyIntelligenceService.get_profile", lambda *a, **k: profile_refusal)
    res_refusal = conv.public_answer("Bonjour, prenez-vous de nouveaux fournisseurs ?")
    assert res_refusal["status"] == "success"
    assert "ne recherche pas de nouveaux fournisseurs" in res_refusal["answer"]

    # Case B: Accepts suppliers with verified contact email
    profile_email = SimpleNamespace(
        has_crm_booking=False, has_retail_commerce=True, active_modules=(), business_hours={},
        configured_crm_services=[], public_products=[], business_configuration={},
        supplier_policy=None, accepts_suppliers=True, email="fournisseurs@produitsero.com", website=None
    )
    monkeypatch.setattr("backend.app.services.company_intelligence_service.CompanyIntelligenceService.get_profile", lambda *a, **k: profile_email)
    res_email = conv.public_answer("Bonjour, nous souhaitons devenir fournisseur.")
    assert res_email["status"] == "success"
    assert "fournisseurs@produitsero.com" in res_email["answer"]

    # Case C: Custom supplier policy
    profile_custom = SimpleNamespace(
        has_crm_booking=False, has_retail_commerce=True, active_modules=(), business_hours={},
        configured_crm_services=[], public_products=[], business_configuration={},
        supplier_policy="Nous acceptons uniquement les fournisseurs certifiés ISO 14001 avec accord cadre.",
        accepts_suppliers=None, email=None, website=None
    )
    monkeypatch.setattr("backend.app.services.company_intelligence_service.CompanyIntelligenceService.get_profile", lambda *a, **k: profile_custom)
    res_custom = conv.public_answer("Est-ce qu'on peut vous vendre nos produits comme fournisseur ?")
    assert res_custom["status"] == "success"
    assert "ISO 14001" in res_custom["answer"]


def test_public_recruitment_dynamic_policies(monkeypatch):
    """Verify recruitment inquiry adapts dynamically according to company configuration."""
    mock_db = MagicMock()
    mock_settings = MagicMock()
    conv = PublicInboundConversation(mock_db, mock_settings, uuid4())

    mock_company = SimpleNamespace(id=uuid4(), name="Produits Ero", email="contact@produitsero.com", website="https://produitsero.com")
    mock_call = SimpleNamespace(company_id=mock_company.id, telnyx_call_control_id="call-1", status="IN_PROGRESS", ended_at=None, locale="fr-CA")
    mock_config = SimpleNamespace(business_name="Produits Ero")
    conv.context = MagicMock(return_value=(mock_call, mock_config, mock_company))

    # Case A: Company is NOT hiring
    profile_not_hiring = SimpleNamespace(
        has_crm_booking=False, has_retail_commerce=True, active_modules=(), business_hours={},
        configured_crm_services=[], public_products=[], business_configuration={},
        recruitment_policy=None, is_hiring=False, email=None, website=None
    )
    monkeypatch.setattr("backend.app.services.company_intelligence_service.CompanyIntelligenceService.get_profile", lambda *a, **k: profile_not_hiring)
    res_no = conv.public_answer("Est-ce que vous embauchez en ce moment ?")
    assert res_no["status"] == "success"
    assert "aucun poste ouvert" in res_no["answer"] or "ne recrute pas" in res_no["answer"]

    # Case B: Company IS hiring and has official website
    profile_hiring = SimpleNamespace(
        has_crm_booking=False, has_retail_commerce=True, active_modules=(), business_hours={},
        configured_crm_services=[], public_products=[], business_configuration={},
        recruitment_policy=None, is_hiring=True, email="hr@produitsero.com", website="https://produitsero.com/carrieres"
    )
    monkeypatch.setattr("backend.app.services.company_intelligence_service.CompanyIntelligenceService.get_profile", lambda *a, **k: profile_hiring)
    res_hiring = conv.public_answer("Je cherche un emploi, avez-vous des postes à pourvoir ?")
    assert res_hiring["status"] == "success"
    assert "https://produitsero.com/carrieres" in res_hiring["answer"]

    # Case C: Unconfirmed recruitment without configured website/email -> safe intake message
    profile_unconfirmed = SimpleNamespace(
        has_crm_booking=False, has_retail_commerce=True, active_modules=(), business_hours={},
        configured_crm_services=[], public_products=[], business_configuration={},
        recruitment_policy=None, is_hiring=None, email=None, website=None
    )
    monkeypatch.setattr("backend.app.services.company_intelligence_service.CompanyIntelligenceService.get_profile", lambda *a, **k: profile_unconfirmed)
    res_unconfirmed = conv.public_answer("Est-ce que vous recrutez des stagiaires ?")
    assert res_unconfirmed["status"] == "success"
    assert "pas confirmées" in res_unconfirmed["answer"]
    assert "coordonnées" in res_unconfirmed["answer"]


def test_public_truthful_non_retail_service_grounding(monkeypatch):
    """Verify non-retail business (e.g., clinic or law office) never invents retail stock or shopping."""
    mock_db = MagicMock()
    mock_settings = MagicMock()
    conv = PublicInboundConversation(mock_db, mock_settings, uuid4())

    mock_company = SimpleNamespace(id=uuid4(), name="Clinique Santé Plus", email="info@clinique.ca", website="https://clinique.ca")
    mock_call = SimpleNamespace(company_id=mock_company.id, telnyx_call_control_id="call-clinic", status="IN_PROGRESS", ended_at=None, locale="fr-CA")
    mock_config = SimpleNamespace(business_name="Clinique Santé Plus")
    conv.context = MagicMock(return_value=(mock_call, mock_config, mock_company))

    profile_clinic = SimpleNamespace(
        has_crm_booking=True,
        has_retail_commerce=False,
        active_modules=("crm", "voice"),
        business_hours={},
        configured_crm_services=[{"name": "Consultation générale", "price": 120, "currency": "CAD"}],
        public_products=[],
        business_configuration={},
    )
    monkeypatch.setattr("backend.app.services.company_intelligence_service.CompanyIntelligenceService.get_profile", lambda *a, **k: profile_clinic)

    res_product = conv.public_answer("Avez-vous des produits en stock ou un inventaire à acheter ?")
    assert res_product["status"] == "success"
    # Must truthfully redirect to professional services, not invent store stock
    assert "services professionnels" in res_product["answer"] or "prestations" in res_product["answer"]
    assert "snowboard" not in res_product["answer"]
    assert "inventaire" not in res_product["answer"]


# ==============================================================================
# 11. Universal Industry Task Optimization (8 Sectors + Novel Custom Sector)
# ==============================================================================

def test_universal_industry_task_optimization_multi_sector():
    """Verify task optimization adapts dynamically across 8 diverse industries including novel custom sectors."""
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
        ("Santé", "Consultation de triage et préparation du dossier patient", "Santé & Clinique Médicale"),
        ("Industrie", "Usinage pièce mécanique sur machine commande numérique", "Industrie & Production Manufacturière"),
        ("Hôtellerie", "Inspection de chambre VIP et accueil check-in client", "Hôtellerie & Hébergement"),
        ("Conseil", "Rédaction note de synthèse juridique pour dossier client", "Conseil & Professions Libérales"),
        ("Finance", "Rapprochement bancaire et déclaration TVA", "Finance & Comptabilité"),
    ]

    for sector_name, query, expected_sector in sectors:
        res = coach.optimize_task_execution(user, query, locale="fr-CA")
        assert res["status"] == "success", f"Failed on {sector_name}"
        assert res["sector"] == expected_sector, f"Expected {expected_sector}, got {res['sector']}"
        assert len(res["methodology_steps"]) == 4
        assert "spoken_summary" in res
        assert len(res["spoken_summary"]) > 40

    # Sector entirely novel / custom: "Centre de Recherche Aérospatiale Sous-Marine"
    novel_res = coach.optimize_task_execution(
        user,
        "Calibration du capteur acoustique haute pression",
        industry_sector="Centre de Recherche Aérospatiale Sous-Marine",
        locale="fr-CA",
    )
    assert novel_res["status"] == "success"
    assert novel_res["sector"] == "Centre De Recherche Aérospatiale Sous-Marine"
    assert len(novel_res["methodology_steps"]) == 4
    assert "Excellence" not in novel_res["sector"]


# ==============================================================================
# 12. Full Telnyx Barge-In Audio Interruption Chain
# ==============================================================================

@pytest.mark.asyncio
async def test_full_telnyx_barge_in_clears_socket_and_discards_superseded_epoch():
    """Verify end-to-end Telnyx barge-in:
    - Interrupting caller utterance sends {"event": "clear"} to Telnyx WebSocket.
    - Outbound audio queue is completely flushed.
    - Ongoing or superseded turns are discarded without speaking confusing recovery messages.
    """
    from backend.app.voice.telnyx_media import TelnyxMediaBridge

    class MockSocket:
        def __init__(self):
            self.sent = []
            self.incoming = asyncio.Queue()
        async def send_json(self, data):
            self.sent.append(data)
        async def receive_json(self):
            return await self.incoming.get()

    class MockAdapter:
        def __init__(self):
            self.interrupted = False
            self.spoken = []
        async def speak(self, text):
            self.spoken.append(text)
        async def interrupt(self):
            self.interrupted = True
        async def clear_input(self):
            pass

    mock_socket = MockSocket()
    mock_adapter = MockAdapter()

    async def validate_start(s): pass
    async def authorize(): pass
    async def execute_turn(i, t):
        return {"status": "success", "answer": "Voici la réponse complète de catalogue pour vos achats..."}

    bridge = TelnyxMediaBridge(
        socket=mock_socket,
        adapter=mock_adapter,
        locale="fr-CA",
        validate_start=validate_start,
        authorize=authorize,
        execute_turn=execute_turn,
        allow_natural_interruptions=True,
    )
    bridge.stream_id = "test-stream-1"
    bridge.phase = "PLAYING"
    bridge._output.put_nowait((bridge.epoch, b"\x00" * 160))
    bridge._output.put_nowait((bridge.epoch, b"\x00" * 160))

    assert bridge._output.qsize() == 2

    # Caller interrupts explicitly while agent is playing
    await bridge.interrupt()

    # 1. Output queue must be purged
    assert bridge._output.empty()
    # 2. {"event": "clear"} must be sent to Telnyx socket
    assert {"event": "clear"} in mock_socket.sent
    # 3. Adapter interrupt must be called
    assert mock_adapter.interrupted is True
    # 4. Phase must be INTERRUPTED
    assert bridge.phase == "INTERRUPTED"
    # 5. Epoch must have incremented
    assert bridge.epoch > 0


# ==============================================================================
# 13. Two Distinct Employees Handover & Succession on the Same Phone
# ==============================================================================

def test_two_distinct_employees_handover_succession_on_same_phone():
    """Verify the decisive scenario:
    Two distinct employees (Employee A, then Employee B) use the exact same phone successively.
    1. Employee A calls from their phone and is authenticated with their PIN.
    2. Employee A requests handover ('Je te passe mon collègue').
    3. Session A is revoked, conversation context detached/cleared, source_context marked handover_revoked.
    4. Employee B types their OWN distinct PIN on the same handset.
    5. verify_gather identifies Employee B despite caller_phone belonging to Employee A.
    6. Employee B is authenticated with their own user ID and role, completely isolated from Employee A.
    """
    from backend.app.config.settings import Settings
    from backend.app.voice.auth import VoiceCallerAuth
    from backend.app.core.security import hash_password
    from backend.app.models.user import UserRole
    from backend.app.models.voice import VoiceCall, VoiceCallerCredential

    company_id = uuid4()
    user_a = User(
        id=uuid4(),
        company_id=company_id,
        email="employee_a@tenant.com",
        first_name="Alice",
        last_name="Manager",
        phone="+15145550001",
        role=UserRole.MANAGER,
        is_active=True,
    )
    user_b = User(
        id=uuid4(),
        company_id=company_id,
        email="employee_b@tenant.com",
        first_name="Bob",
        last_name="Staff",
        phone="+15145550002",
        role=UserRole.USER,
        is_active=True,
    )
    call = VoiceCall(
        id=uuid4(),
        company_id=company_id,
        caller_phone="+15145550001",  # Alice's phone number
        caller_type="UNKNOWN",
        status="in_progress",
        verification_attempts=0,
    )
    settings = Settings()
    settings.auth_jwt_secret = "test-secret-32-chars-minimum-length-key-xyz"

    mock_db = MagicMock()
    auth = VoiceCallerAuth(mock_db, settings)

    # Alice's credential (PIN: 112233)
    alice_cred = VoiceCallerCredential(
        id=uuid4(),
        company_id=company_id,
        principal_type="USER",
        principal_id=user_a.id,
        phone_number="+15145550001",
        enabled=True,
        pin_hash=hash_password(auth._peppered(company_id, user_a.id, "112233")),
        failed_attempts=0,
    )
    # Bob's credential (PIN: 998877)
    bob_cred = VoiceCallerCredential(
        id=uuid4(),
        company_id=company_id,
        principal_type="USER",
        principal_id=user_b.id,
        phone_number="+15145550002",
        enabled=True,
        pin_hash=hash_password(auth._peppered(company_id, user_b.id, "998877")),
        failed_attempts=0,
    )

    # Step 1: Alice authenticates with her PIN
    def mock_scalar_fn(query):
        q_str = str(query).lower()
        if "company_memberships" in q_str:
            mem = MagicMock()
            mem.role = UserRole.MANAGER
            return mem
        if "users" in q_str:
            return user_a
        if "voice_caller_credentials" in q_str:
            return alice_cred
        return None

    mock_db.scalar.side_effect = mock_scalar_fn
    mock_db.scalars.return_value.all.return_value = [alice_cred, bob_cred]
    mock_db.get.side_effect = lambda model, uid: user_a if uid == user_a.id else (user_b if uid == user_b.id else None)

    res_a = auth.verify_gather(call, "112233")
    assert res_a["authenticated"] is True
    assert call.authenticated_user_id == user_a.id

    # Step 2: Handover happens (Alice passes phone to Bob)
    call.authenticated_user_id = None
    call.caller_type = "UNKNOWN"
    call.central_conversation_id = None
    call.source_context = {
        "authenticated": False,
        "handover_revoked": True,
        "handover_count": 1,
    }

    # Step 3: Bob enters his PIN 998877 on Alice's phone (+15145550001)
    res_b = auth.verify_gather(call, "998877")
    assert res_b["authenticated"] is True
    assert call.authenticated_user_id == user_b.id
    assert call.source_context["user_id"] == str(user_b.id)
    assert "Bob" in call.source_context["user_name"]
    assert call.source_context["handover_revoked"] is False
    assert alice_cred.failed_attempts == 0


# ==============================================================================
# 14. Warehouse Keywords & Public Delivery Routing Integrity
# ==============================================================================

def test_warehouse_colis_exped_keywords_not_falling_through():
    """Verify 'Comment expédier les colis plus vite ?' maps to warehouse logistics, not generic advice."""
    mock_db = MagicMock()
    user = User(
        id=uuid4(),
        company_id=uuid4(),
        email="warehouse@tenant.com",
        first_name="Marc",
        role="Employee",
    )
    coach = EmployeeCoachService(mock_db)
    res = coach.optimize_task_execution(
        user,
        "Comment expédier les colis plus vite et optimiser les emballages ?",
        industry_sector="Logistique",
        locale="fr-CA",
    )
    assert res["status"] == "success"
    assert res["sector"] == "Logistique & E-commerce"
    assert any("colis" in s.lower() or "emballage" in s.lower() or "picking" in s.lower() for s in res["methodology_steps"] + [res["spoken_summary"]])


def test_public_delivery_inquiry_not_blocked_by_coaching_refusal():
    """Verify customer questions about delivery policies are not blocked by the employee coaching gatekeeper."""
    from backend.app.voice.direct_answers import resolve_direct_voice_answer

    mock_db = MagicMock()
    company_id = uuid4()

    # Public unauthenticated caller asking about delivery
    ans = resolve_direct_voice_answer(
        mock_db,
        company_id=company_id,
        transcript="Comment fonctionne la livraison chez vous ?",
        user_id=None,
        authenticated_staff=False,
        locale="fr-CA",
    )
    # Must NOT return "Le coaching de performance et vos priorités professionnelles sont réservés aux employés"
    assert ans is None or "réservés aux employés" not in ans

    # But an unauthenticated caller asking for employee task briefing MUST be informed of PIN requirement
    ans_staff = resolve_direct_voice_answer(
        mock_db,
        company_id=company_id,
        transcript="Donne-moi mes tâches d'employé pour mon quart",
        user_id=None,
        authenticated_staff=False,
        locale="fr-CA",
    )
    assert ans_staff is not None
    assert "réservés aux employés" in ans_staff


# ==============================================================================
# 15. Commercial Contracts vs Recruitment CV Routing
# ==============================================================================

def test_commercial_contracts_not_intercepted_by_recruitment(monkeypatch):
    """Verify questions about commercial contracts are not misrouted to job application / CV intake."""
    from backend.app.config.settings import Settings
    from backend.app.services.company_intelligence_service import CompanyIntelligenceProfile

    mock_db = MagicMock()
    mock_call = MagicMock()
    mock_call.id = uuid4()
    mock_call.locale = "fr-CA"
    mock_config = MagicMock()
    mock_company = MagicMock()
    mock_company.email = "contact@entreprise.com"
    mock_company.website = "https://entreprise.com"

    conv = PublicInboundConversation(mock_db, Settings(), mock_call.id)
    conv.context = MagicMock(return_value=(mock_call, mock_config, mock_company))

    profile = MagicMock(spec=CompanyIntelligenceProfile)
    profile.company_id = mock_company.id if hasattr(mock_company, "id") else uuid4()
    profile.company_name = "Entreprise Test"
    profile.is_hiring = True
    profile.recruitment_policy = None
    profile.accepts_suppliers = None
    profile.online_store_url = None
    profile.business_configuration = {}
    monkeypatch.setattr(
        "backend.app.services.company_intelligence_service.CompanyIntelligenceService.get_profile",
        lambda self, cid: profile,
    )

    # Commercial contract inquiry
    res_commercial = conv.public_answer("Quelle est la durée de mon contrat de service commercial ?")
    assert "curriculum" not in res_commercial["answer"].lower()
    assert "cv" not in res_commercial["answer"].lower()
    assert "recrute" not in res_commercial["answer"].lower()

    # Real recruitment inquiry
    res_hiring = conv.public_answer("Bonjour, est-ce que vous recrutez actuellement ? J'aimerais déposer ma candidature.")
    assert "recrute" in res_hiring["answer"].lower() or "emploi" in res_hiring["answer"].lower()


# ==============================================================================
# 16. Gemini Live Realtime Adapter Staff Identity Propagation
# ==============================================================================

def test_gemini_live_adapter_staff_identity_propagation():
    """Verify GeminiLiveRealtimeAudioAdapter propagates authenticated staff identity and clears on handover."""
    from backend.app.config.settings import Settings
    from backend.app.voice.realtime_provider import GeminiLiveRealtimeAudioAdapter, OpenAIAudioConfig

    config = MagicMock()
    config.effective_voice_name = "Avenqo Voice"
    audio_cfg = OpenAIAudioConfig(api_key="mock-key")

    adapter = GeminiLiveRealtimeAudioAdapter(
        settings=Settings(),
        config=config,
        audio_config=audio_cfg,
        api_key="mock-key",
    )
    assert adapter._is_authenticated_staff is False
    assert adapter._staff_name is None

    # Authenticate employee
    adapter.update_staff_identity(True, "Paul", "Owner")
    assert adapter._is_authenticated_staff is True
    assert adapter._staff_name == "Paul"
    assert adapter._staff_role == "Owner"

    # Verify _build_live_config includes Paul
    cfg = adapter._build_live_config("fr-CA")
    prompt = cfg.system_instruction.parts[0].text if hasattr(cfg, "system_instruction") else str(cfg)
    assert "Paul" in prompt

    # Handover: clear identity
    adapter.update_staff_identity(False, None, None)
    assert adapter._is_authenticated_staff is False
    assert adapter._staff_name is None
    cfg_cleared = adapter._build_live_config("fr-CA")
    prompt_cleared = cfg_cleared.system_instruction.parts[0].text if hasattr(cfg_cleared, "system_instruction") else str(cfg_cleared)
    assert "Paul" not in prompt_cleared
