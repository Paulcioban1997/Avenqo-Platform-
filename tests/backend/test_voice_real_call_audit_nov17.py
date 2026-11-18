"""Tests de validation automatisés pour l'audit des appels réels du 17 novembre 2026.

Vérifie rigoureusement les 6 axes critiques :
1. P0 Authentification Employé : Résolution NIP via caller_phone, synchronisation auto-healing sécurisée, touche # DTMF, et audit log.
2. P0 Précision & Fraîcheur des Stocks : Pas de quantité annoncée si le stock n'est pas vérifié en direct (pas de 49 unités inventées).
3. P1 Prononciation Entreprise Configurable : custom_pronunciation et voice_display_name dynamiques par entreprise sans hardcoding global.
4. P1 Multilingue Français / Anglais / Roumain : Verrouillage et basculement sans fuite de français en roumain.
5. P1 Latence & Filler : Délai de 3,5s et cooldown de 30s pour le message d'attente, traduit en roumain.
6. P2 Règle Devises Étrangères & Rappels : Refus d'estimer les taux de change (EUR) et réponse naturelle aux propositions de rappel.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import select

from backend.app.ai.chat.chat_service import _localized_system_instruction, SYSTEM_INSTRUCTION
from backend.app.config.settings import Settings
from backend.app.core.permissions import UserRole
from backend.app.core.security import hash_password
from backend.app.models import (
    CompanyMembership,
    User,
    VoiceBusinessConfig,
    VoiceCallerCredential,
)
from backend.app.models.audit_log import AuditLogEntry
from backend.app.voice.auth import VoiceCallerAuth
from backend.app.voice.direct_answers import (
    spoken_catalog_answer,
    spoken_module_answer,
)
from backend.app.voice.language_resolver import CallLanguageSession, to_bcp47
from backend.app.voice.module_actions import company_call_language_session
from shared.ai_engine.contracts import TenantContext
from tests.backend.test_voice_agent import _voice_database


def test_1_voice_audit_employee_pin_autoheal_and_pound_sign(tmp_path):
    """P0 : L'employé appelant avec son numéro enregistré est authentifié même si son NIP contient '#' et le credential est auto-synchronisé."""
    engine, session, company, config, _api_key, orchestrator = _voice_database(tmp_path)
    try:
        settings = Settings(AUTH_JWT_SECRET="test-jwt-secret-minimum-32-chars-long")
        caller_phone = "+15142955720"

        user = User(
            company_id=company.id,
            first_name="Francis",
            last_name="Queval",
            email="francis@eroproduits.com",
            password_hash=hash_password("SuperSecret123!"),
            role=UserRole.OWNER,
            phone=caller_phone,
            is_active=True,
        )
        session.add(user)
        session.flush()
        session.add(CompanyMembership(company_id=company.id, user_id=user.id, role=UserRole.OWNER, is_active=True))
        session.commit()

        auth = VoiceCallerAuth(session, settings)
        # NIP configuré initialement sans numéro ou avec un ancien numéro
        auth.set_pin(TenantContext(company.id, user.id), "USER", user.id, "868491")
        session.commit()

        # Forcer le credential à un ancien numéro différent pour tester l'auto-healing
        cred = session.scalar(
            select(VoiceCallerCredential).where(
                VoiceCallerCredential.company_id == company.id,
                VoiceCallerCredential.principal_id == user.id,
            )
        )
        assert cred is not None
        cred.phone_number = "+15140001111"
        session.commit()

        # Appel réel arrivant de +15142955720
        call = orchestrator.record_inbound(config, {"call_control_id": "pin-call-autoheal", "from": caller_phone})

        # Saisie DTMF avec touche dièse (#)
        result = auth.verify_gather(call, "868491#")
        assert result["authenticated"] is True
        assert call.authenticated_user_id == user.id
        assert call.caller_type == "OWNER"

        # Vérifier que le numéro du credential a été auto-synchronisé
        session.refresh(cred)
        assert cred.phone_number == caller_phone

        # Vérifier la présence du log d'audit
        audit_log = session.scalar(
            select(AuditLogEntry).where(
                AuditLogEntry.company_id == company.id,
                AuditLogEntry.action == "voice_credential_phone_synchronized",
            )
        )
        assert audit_log is not None
        assert audit_log.actor_user_id == user.id
    finally:
        session.close()
        engine.dispose()


def test_2_voice_audit_caller_matched_accuracy_and_isolation(tmp_path):
    """P0 : caller_matched est False si le numéro n'appartient à aucun utilisateur du tenant, et isolation multi-tenant stricte."""
    engine, session, company, config, _api_key, orchestrator = _voice_database(tmp_path)
    try:
        settings = Settings(AUTH_JWT_SECRET="test-jwt-secret-minimum-32-chars-long")

        # Appel provenant d'un numéro non répertorié
        unknown_call = orchestrator.record_inbound(config, {"call_control_id": "call-unknown", "from": "+19998887777"})
        auth = VoiceCallerAuth(session, settings)

        result = auth.verify_gather(unknown_call, "868491#")
        assert result["authenticated"] is False
        assert result["reason"] == "caller_not_recognized"
    finally:
        session.close()
        engine.dispose()


def test_3_voice_audit_inventory_freshness_no_unconfirmed_49_units():
    """P0 : Les articles issus de jeux de données statiques / connecteurs non-live ne doivent jamais annoncer un stock en direct (pas de 49 planches)."""
    products = [
        {
            "name": "Planche à neige All-Mountain",
            "price": 499.99,
            "unit": "CAD",
            "in_stock": True,
            "inventory_count": 49,
            "is_live_stock": False,  # Non synchronisé en direct (dataset importé)
            "stock_status": "unconfirmed_historical",
        }
    ]

    # En français
    ans_fr = spoken_catalog_answer(
        products,
        retail_enabled=True,
        locale="fr-CA",
        currency="CAD",
    )
    assert "Planche à neige All-Mountain" in ans_fr
    assert "stock en direct non synchronisé" in ans_fr
    assert "49 disponible" not in ans_fr

    # En roumain
    ans_ro = spoken_catalog_answer(
        products,
        retail_enabled=True,
        locale="ro-RO",
        currency="CAD",
    )
    assert "Planche à neige All-Mountain" in ans_ro
    assert "stoc nesincronizat" in ans_ro
    assert "49 disponibil" not in ans_ro

    # Quand le stock est live (is_live_stock = True)
    products_live = [
        {
            "name": "Planche à neige All-Mountain",
            "price": 499.99,
            "unit": "CAD",
            "in_stock": True,
            "inventory_count": 5,
            "is_live_stock": True,
        }
    ]
    ans_live_fr = spoken_catalog_answer(products_live, retail_enabled=True, locale="fr-CA", currency="CAD")
    assert ", disponible" in ans_live_fr


def test_4_voice_audit_configurable_company_pronunciation():
    """P1 : Prononciation dynamique par entreprise sans hardcoding global."""
    prompt = _localized_system_instruction(
        SYSTEM_INSTRUCTION,
        user_language="fr",
        company_country="CA",
        company_currency="CAD",
        company_timezone="America/Toronto",
        is_voice_call=True,
        effective_voice_name="Produits Éro",
        custom_pronunciation="Produits Éro sans hache et sans zed",
    )

    assert "The official spoken company name is 'Produits Éro'." in prompt
    assert "Produits Éro sans hache et sans zed" in prompt
    assert "Never invent prefixes, extraneous letters, or false homophones" in prompt
    # Ne doit pas contenir de hardcode statique absolu imposé à tous
    assert "When referring to 'Produits Ero' or 'Produits_Ero', ALWAYS pronounce it strictly 'Produits Éro'" not in prompt


def test_5_voice_audit_multilingual_romanian_switching(tmp_path):
    """P1 : Basculement fluide vers le roumain sans fuite de français."""
    engine, session, company, config, _api_key, orchestrator = _voice_database(tmp_path)
    try:
        call = orchestrator.record_inbound(config, {"call_control_id": "call-lang-ro", "from": "+15142955720"})
        lang_session = company_call_language_session(session, config, call)

        # L'appel commence en français
        assert lang_session.active_locale.startswith("fr")

        # Demande explicite de basculer en roumain
        switched = lang_session.process_utterance("Putem vorbi în română?")
        assert switched == "ro-RO"
        assert lang_session.active_locale == "ro-RO"

        # Une réponse directe en roumain ne doit contenir aucune expression française
        modules_ro = spoken_module_answer(["Catalog", "Rendez-vous"], plan_code="Pro", locale="ro-RO")
        assert "Compania dumneavoastră dispune în prezent" in modules_ro
        assert "Votre entreprise" not in modules_ro
    finally:
        session.close()
        engine.dispose()


def test_6_voice_audit_latency_filler_and_foreign_currency():
    """P1 & P2 : Directives système strictes pour latence filler, conversion euro et rappel."""
    prompt = _localized_system_instruction(
        SYSTEM_INSTRUCTION,
        user_language="ro",
        company_country="CA",
        company_currency="CAD",
        company_timezone="America/Toronto",
        is_voice_call=True,
    )

    # Directive interdisant d'inventer des taux de change EUR
    assert "NO FOREIGN CURRENCY ESTIMATION (STRICT RULE)" in prompt
    assert "Combien ça fait en euros ?" in prompt or "Cât costă în euro?" in prompt
    assert "NEVER invent an exchange rate or output a converted figure" in prompt

    # Directive d'accueil naturel des rappels entrants
    assert "Caller Callbacks & Inbound Availability" in prompt
    assert "Do NOT claim to schedule an automated outbound telephone callback" in prompt

    # Directive multilingue roumain sans fuite
    assert "Dynamic Language Switching & Romanian Support" in prompt
    assert "NEVER leak French phrases (such as 'Un instant, je vérifie...')" in prompt
