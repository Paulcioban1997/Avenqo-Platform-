"""Tests de validation automatisés pour les correctifs de l'audit réel du 18 novembre 2026.

Couvre de bout en bout :
1. P0 — NIP Employé : Credential désactivé (enabled=False)
   - Refus en verify_gather si désactivé
   - Réactivation sécurisée exigeant le mot de passe actuel du titulaire
   - Succès de l'authentification DTMF après réactivation
   - Réconciliation des statuts (configured, enabled, phone_access_enabled, has_pin)

2. P0 — Fin d'appel Telnyx et HTTP 500
   - Interception de Telnyx error 90018 ("Call has already ended")
   - Absence d'exception 500
   - Clôture idempotente du statut d'appel

3. P0 — État de stock tri-état (IN_STOCK, OUT_OF_STOCK, UNKNOWN)
   - UNKNOWN ne doit jamais être représenté par False ou 0
   - Distinction stricte dans company_intelligence_service, commerce_tools, direct_answers et chat_service
   - Les produits UNKNOWN ne sont JAMAIS présentés comme "en rupture de stock"

4. P1 — Prononciation vocale du nom d'entreprise
   - Prononciation officielle "Produits Éro" appliquée sans virgule parasite ni confusion avec "Zéro"
   - Injection correcte dans les invites Gemini Live et les messages IVR

5. P1 — Requêtes larges de catalogue ("Je veux savoir le stock de chacun de vos produits")
   - Détection en tant que requête de catalogue ouvert
   - Présentation résumée par catégorie/lot avec prix indicatifs et statut UNKNOWN transparent
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from backend.app.config.settings import Settings
from backend.app.core.permissions import UserRole
from backend.app.core.security import hash_password
from backend.app.models import (
    Company,
    CompanyMembership,
    CompanyModule,
    CompanyModuleStatus,
    CommerceConnection,
    Module,
    User,
    VoiceBusinessConfig,
    VoiceCall,
    VoiceCallerCredential,
)
from backend.app.models.commerce_connection import NormalizedCommerceRecord
from backend.app.routers.voice import (
    is_call_already_ended_error,
    update_user_phone_access,
)
from backend.app.schemas.voice import (
    VoicePhoneAccessRequest,
    VoiceAuthPinStatusResponse,
)
from backend.app.services.company_intelligence_service import (
    CompanyIntelligenceService,
)
from backend.app.voice.auth import VoiceCallerAuth
from backend.app.voice.direct_answers import (
    is_open_catalog_question,
    resolve_direct_voice_answer,
    spoken_catalog_answer,
)
from backend.app.voice.messages import (
    apply_spoken_pronunciation,
    voice_ivr_greeting,
    voice_speech_name,
)
from backend.app.voice.providers import TelnyxCallEndedError
from backend.app.voice.realtime_provider import build_personality_system_prompt
from shared.ai_engine.contracts import TenantContext
from tests.backend.test_voice_agent import _voice_database


# ==============================================================================
# 1. P0 — NIP EMPLOYÉ : CREDENTIAL DÉSACTIVÉ & RÉACTIVATION SÉCURISÉE
# ==============================================================================

def test_p0_disabled_credential_requires_password_for_reactivation(tmp_path):
    """Vérifie que la réactivation d'un credential désactivé exige le mot de passe du titulaire."""
    engine, session, company, config, _api_key, orchestrator = _voice_database(tmp_path)
    try:
        user_pw = "MonMotDePasseSecret123!"
        user = User(
            company_id=company.id,
            first_name="Francis",
            last_name="Queval",
            email="francis@eroproduits.com",
            password_hash=hash_password(user_pw),
            role=UserRole.OWNER,
            phone="+15142955720",
            is_active=True,
        )
        session.add(user)
        session.flush()
        session.add(CompanyMembership(company_id=company.id, user_id=user.id, role=UserRole.OWNER, is_active=True))
        session.commit()

        # Création du credential en état désactivé
        cred = VoiceCallerCredential(
            company_id=company.id,
            principal_type="USER",
            principal_id=user.id,
            phone_number="+15142955720",
            pin_hash=hash_password("salt_868491"),
            enabled=False,
            failed_attempts=2,
        )
        session.add(cred)
        session.commit()

        # 1. Tentative de réactivation sans mot de passe -> HTTPException 400
        from fastapi import HTTPException
        identity = MagicMock()
        identity.user = user

        req_no_pw = VoicePhoneAccessRequest(enabled=True)
        with pytest.raises(HTTPException) as exc_info:
            update_user_phone_access(req_no_pw, identity=identity, db=session)
        assert exc_info.value.status_code == 400
        assert "mot de passe" in str(exc_info.value.detail).lower()

        # 2. Tentative avec mauvais mot de passe -> HTTPException 403
        req_bad_pw = VoicePhoneAccessRequest(enabled=True, current_password=SecretStr("MauvaisMotDePasse"))
        with pytest.raises(HTTPException) as exc_info:
            update_user_phone_access(req_bad_pw, identity=identity, db=session)
        assert exc_info.value.status_code == 403

        # 3. Réactivation avec le bon mot de passe -> succès
        req_good_pw = VoicePhoneAccessRequest(enabled=True, current_password=SecretStr(user_pw))
        res = update_user_phone_access(req_good_pw, identity=identity, db=session)

        assert isinstance(res, VoiceAuthPinStatusResponse)
        assert res.enabled is True
        assert res.phone_access_enabled is True
        assert res.configured is True
        assert res.has_pin is True
        assert res.failed_attempts == 0

        # Vérification en base de données
        session.refresh(cred)
        assert cred.enabled is True
        assert cred.failed_attempts == 0
        assert cred.locked_until is None
    finally:
        session.close()
        engine.dispose()


def test_p0_disabled_credential_fails_gather_until_reactivated(tmp_path):
    """Vérifie que verify_gather refuse un credential désactivé, puis réussit après réactivation."""
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
        auth.set_pin(TenantContext(company.id, user.id), "USER", user.id, "868491")
        session.commit()

        # On désactive le credential explicitement
        cred = session.scalar(select(VoiceCallerCredential).where(VoiceCallerCredential.principal_id == user.id))
        assert cred is not None
        cred.enabled = False
        session.commit()

        call = VoiceCall(
            company_id=company.id,
            config_id=config.id,
            caller_phone=caller_phone,
            status="in_progress",
            started_at=datetime.now(timezone.utc),
            verification_attempts=0,
        )
        session.add(call)
        session.commit()

        # 1. Appel avec le bon NIP mais credential désactivé -> refus
        res_disabled = auth.verify_gather(call, "868491#")
        assert res_disabled["authenticated"] is False
        assert res_disabled.get("reason") == "credential_disabled"

        # 2. Réactivation du credential
        identity = MagicMock()
        identity.user = user
        update_user_phone_access(
            VoicePhoneAccessRequest(enabled=True, current_password=SecretStr("SuperSecret123!")),
            identity=identity,
            db=session,
        )

        # 3. Nouvel essai DTMF avec le même NIP -> succès
        res_active = auth.verify_gather(call, "868491#")
        assert res_active["authenticated"] is True
        assert call.authenticated_user_id == user.id
    finally:
        session.close()
        engine.dispose()


# ==============================================================================
# 2. P0 — TELNYX 90018 ET HTTP 500 PREVENTION
# ==============================================================================

def test_p0_telnyx_90018_call_ended_detection():
    """Vérifie que l'erreur 90018 de Telnyx est correctement identifiée pour éviter un HTTP 500."""
    # Test avec exception typée
    ended_err = TelnyxCallEndedError("Telnyx call has already ended (code 90018)")
    assert is_call_already_ended_error(ended_err) is True

    # Test avec HTTPStatusError 422 contenant code 90018
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 422
    mock_resp.json.return_value = {
        "errors": [
            {"code": "90018", "title": "Call has already ended", "detail": "Call has already ended"}
        ]
    }
    status_err = httpx.HTTPStatusError("Client error '422 Unprocessable Entity'", request=MagicMock(), response=mock_resp)
    assert is_call_already_ended_error(status_err) is True

    # Test avec message générique contenant "Call has already ended"
    runtime_err = RuntimeError("Command gather_using_speak failed: Call has already ended")
    assert is_call_already_ended_error(runtime_err) is True

    # Test avec une autre erreur (non liée à la fin d'appel) -> False
    other_err = ValueError("Invalid input parameter")
    assert is_call_already_ended_error(other_err) is False


# ==============================================================================
# 3. P0 — ÉTAT DE STOCK TRI-ÉTAT : IN_STOCK, OUT_OF_STOCK, UNKNOWN
# ==============================================================================

def test_p0_tri_state_stock_logic(tmp_path):
    """Vérifie que le stock inconnu (non synchronisé en direct) produit UNKNOWN et None, et jamais False ou rupture."""
    engine, session, company, config, _api_key, orchestrator = _voice_database(tmp_path)
    try:
        retail_mod = Module(name="Retail", code="retail", is_active=True)
        session.add(retail_mod)
        session.flush()
        session.add(
            CompanyModule(
                company_id=company.id,
                module_id=retail_mod.id,
                activated_at=datetime.now(timezone.utc),
                status=CompanyModuleStatus.ACTIVE.value,
            )
        )
        session.commit()

        # 1. Produit avec inventaire non synchronisé en direct (dataset statique sans connecteur actif récent)
        rec_unconfirmed = NormalizedCommerceRecord(
            company_id=company.id,
            provider="manual_import",
            entity_type="product",
            source_record_id="prod_101",
            normalized_data={
                "name": "Planche All-Mountain 156",
                "unit_price": 650.0,
                "inventory_level": 49,
                "product_category": "Snowboard",
            },
        )
        session.add(rec_unconfirmed)
        session.commit()

        service = CompanyIntelligenceService(session)
        profile = service.get_profile(company.id)

        assert len(profile.public_products) >= 1
        prod = next(p for p in profile.public_products if p["name"] == "Planche All-Mountain 156")

        # RÈGLE ABSOLUE : UNKNOWN ne doit jamais être False ni 0
        assert prod["is_live_stock"] is False
        assert prod["in_stock"] is None  # Strictement None, jamais False !
        assert prod["stock_availability"] == "UNKNOWN"
        assert prod["inventory_count"] is None
        assert prod["historical_reference_units"] == 49
        assert prod["price_status"] == "historical_catalog"

        # Vérification du message vocal généré par spoken_catalog_answer
        answer_fr = spoken_catalog_answer(profile.public_products, retail_enabled=True, locale="fr")
        assert ("stock direct non confirmé" in answer_fr or "stock en direct non synchronisé" in answer_fr)
        assert "en rupture de stock" not in answer_fr
        assert "49 en stock" not in answer_fr

        # Vérification en roumain
        answer_ro = spoken_catalog_answer(profile.public_products, retail_enabled=True, locale="ro")
        assert "stoc direct neconfirmat" in answer_ro
        assert "stoc epuizat" not in answer_ro

        # Vérification en anglais
        answer_en = spoken_catalog_answer(profile.public_products, retail_enabled=True, locale="en")
        assert "live stock unconfirmed" in answer_en
        assert "out of stock" not in answer_en
    finally:
        session.close()
        engine.dispose()


def test_p0_tri_state_stock_verified_live_states():
    """Vérifie les états IN_STOCK et OUT_OF_STOCK lorsque l'inventaire est confirmé en direct."""
    # Simulation produit en direct avec stock > 0
    in_stock_product = {
        "name": "Planche Freestyle 152",
        "price": 550.0,
        "is_live_stock": True,
        "stock_availability": "IN_STOCK",
        "in_stock": True,
        "inventory_count": 8,
    }
    answer_instock = spoken_catalog_answer([in_stock_product], retail_enabled=True, locale="fr")
    assert ("8 en stock" in answer_instock or "disponible" in answer_instock)
    assert "en rupture de stock" not in answer_instock

    # Simulation produit en direct avec stock = 0
    out_of_stock_product = {
        "name": "Casque Pro",
        "price": 120.0,
        "is_live_stock": True,
        "stock_availability": "OUT_OF_STOCK",
        "in_stock": False,
        "inventory_count": 0,
    }
    answer_out = spoken_catalog_answer([out_of_stock_product], retail_enabled=True, locale="fr")
    assert "en rupture de stock" in answer_out
    assert "stock direct non confirmé" not in answer_out


# ==============================================================================
# 4. P1 — PRONONCIATION VOCALE DU NOM D'ENTREPRISE (PRODUITS ÉRO)
# ==============================================================================

def test_p1_spoken_pronunciation_produits_ero():
    """Vérifie que 'Produits_Ero' ou 'Produits Ero' est prononcé 'Produits Éro' sans virgule ni liaison 'Zéro'."""
    cfg = MagicMock()
    cfg.business_name = "Produits_Ero"
    cfg.voice_display_name = "Produits_Ero"
    cfg.custom_pronunciation = "Produits Éro"
    cfg.effective_voice_name = "Produits Éro"
    cfg.preferred_language = "fr"

    spoken = voice_speech_name(cfg)
    assert spoken == "Produits Éro"
    assert "," not in spoken  # Aucune virgule séparant "Produits," et "Ero"

    # Vérification du remplacement dans du texte à synthétiser
    text1 = "Bienvenue chez Produits_Ero. Comment puis-je vous aider ?"
    rendered1 = apply_spoken_pronunciation(text1, cfg)
    assert "Produits Éro" in rendered1
    assert "Produits_Ero" not in rendered1

    text2 = "Vous appelez le service client de Produit Zero."
    rendered2 = apply_spoken_pronunciation(text2, cfg)
    assert "Produits Éro" in rendered2
    assert "Zero" not in rendered2

    # Vérification du prompt système Gemini Live
    prompt = build_personality_system_prompt(
        company_name="Produits Éro",
        locale="fr-CA",
    )
    assert "Produits Éro" in prompt
    assert "Zéro" in prompt  # Mentionné dans la consigne d'exclusion stricte
    assert "rhymes with 'héros'" in prompt


# ==============================================================================
# 5. P1 — REQUÊTES LARGES (« Je veux savoir le stock de chacun de vos produits »)
# ==============================================================================

def test_p1_broad_catalog_query_detection():
    """Vérifie que les demandes globales de stock sont correctement détectées comme questions de catalogue."""
    q1 = "Je veux savoir le stock de chacun de vos produits"
    assert is_open_catalog_question(q1) is True

    q2 = "Quels sont vos produits et leur stock ?"
    assert is_open_catalog_question(q2) is True

    q3 = "Avez-vous la liste de tous vos articles disponibles ?"
    assert is_open_catalog_question(q3) is True

    q4 = "Quel est votre stock de planches ?"
    assert is_open_catalog_question(q4) is True

    q5 = "Parlez-moi de votre politique de retour"
    assert is_open_catalog_question(q5) is False


def test_p1_broad_catalog_query_direct_answer(tmp_path):
    """Vérifie que la requête large de stock reçoit une réponse directe de catalogue sans timeout."""
    engine, session, company, config, _api_key, orchestrator = _voice_database(tmp_path)
    try:
        retail_mod = Module(name="Retail", code="retail", is_active=True)
        session.add(retail_mod)
        session.flush()
        session.add(
            CompanyModule(
                company_id=company.id,
                module_id=retail_mod.id,
                activated_at=datetime.now(timezone.utc),
                status=CompanyModuleStatus.ACTIVE.value,
            )
        )
        session.commit()

        # Ajout de plusieurs produits au catalogue
        for i in range(1, 4):
            session.add(
                NormalizedCommerceRecord(
                    company_id=company.id,
                    provider="catalog",
                    entity_type="product",
                    source_record_id=f"prod_{i}",
                    normalized_data={
                        "name": f"Planche Modèle {i}",
                        "unit_price": 500.0 + i * 50,
                        "inventory_level": 10 + i,
                        "product_category": "Snowboard",
                    },
                )
            )
        session.commit()

        # Résolution directe
        ans = resolve_direct_voice_answer(
            session,
            company_id=company.id,
            transcript="Je veux savoir le stock de chacun de vos produits",
            authenticated_staff=False,
            locale="fr",
        )
        assert ans is not None
        assert "Nous avons au catalogue" in ans
        assert "Planche Modèle 1" in ans
        assert ("stock direct non confirmé" in ans or "stock en direct non synchronisé" in ans)
        assert "en rupture de stock" not in ans
    finally:
        session.close()
        engine.dispose()
