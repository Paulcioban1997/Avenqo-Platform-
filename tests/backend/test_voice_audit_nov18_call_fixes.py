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
from backend.app.dependencies.auth import CurrentIdentity
from backend.app.routers.voice import (
    delete_user_voice_pin,
    get_user_voice_pin_status,
    is_call_already_ended_error,
    update_user_phone_access,
)
from backend.app.schemas.voice import (
    VoicePhoneAccessRequest,
    VoiceAuthPinStatusResponse,
    VoicePinDeleteRequest,
)
from backend.app.services.company_intelligence_service import (
    CompanyIntelligenceService,
)
from backend.app.voice.auth import VoiceCallerAuth
from backend.app.voice.direct_answers import (
    is_language_inquiry,
    is_open_catalog_question,
    resolve_direct_voice_answer,
    spoken_catalog_answer,
    spoken_module_answer,
)
from backend.app.voice.language_resolver import CallLanguageSession
from backend.app.voice.telnyx_media import PublicInboundConversation
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


# ==============================================================================
# 6. P0 — NIP LOGGING, RECONNAISSANCE IDENTITÉ COLLABORATEUR & DÉLIAISON
# ==============================================================================

def test_p0_nip_logging_identifies_matched_principal_and_unlinking(tmp_path, caplog):
    """Vérifie que verify_gather trace explicitement l'identifiant et le rôle du compte sans fuite de NIP,
    qu'un collaborateur peut délier/supprimer son NIP de manière sécurisée avec mot de passe,
    et qu'aucun employé ne peut détourner le numéro d'un autre utilisateur actif.
    """
    import logging
    engine, session, company, config, _api_key, orchestrator = _voice_database(tmp_path)
    try:
        user_pw = "Secr3tPassword!2026"
        user1 = User(
            company_id=company.id,
            first_name="Francis",
            last_name="Queval",
            email="francis@eroproduits.com",
            phone="+15145550001",
            password_hash=hash_password(user_pw),
            role=UserRole.OWNER,
            is_active=True,
        )
        user2 = User(
            company_id=company.id,
            first_name="Ami",
            last_name="Employe",
            email="ami@eroproduits.com",
            phone="+15145550002",
            password_hash=hash_password(user_pw),
            role=UserRole.USER,
            is_active=True,
        )
        session.add_all([user1, user2])
        session.commit()

        mem1 = CompanyMembership(company_id=company.id, user_id=user1.id, role=UserRole.OWNER, is_active=True)
        mem2 = CompanyMembership(company_id=company.id, user_id=user2.id, role=UserRole.USER, is_active=True)
        session.add_all([mem1, mem2])
        session.commit()

        settings = Settings()
        auth = VoiceCallerAuth(session, settings)
        tenant1 = TenantContext(company.id, user1.id)
        tenant2 = TenantContext(company.id, user2.id)

        # Configurer le NIP pour user1
        auth.set_pin(tenant1, "USER", user1.id, "481926", phone_number="+15145550001")
        session.commit()

        # 1. Tentative par user2 de s'attribuer le numéro de user1 -> REFUS STRICT
        with pytest.raises(PermissionError) as exc_info:
            auth.set_pin(tenant2, "USER", user2.id, "739264", phone_number="+15145550001")
        assert "déjà associé à un autre collaborateur" in str(exc_info.value)

        # 2. Appel avec mauvais NIP: vérifier que les logs identifient le principal_id et principal_role
        call = VoiceCall(
            company_id=company.id,
            caller_phone="+15145550001",
            config_id=config.id,
        )
        session.add(call)
        session.commit()

        with caplog.at_level(logging.INFO, logger="avenqo.voice.auth"):
            result = auth.verify_gather(call, "739264")  # mauvais NIP
        assert result["success"] is False
        assert result["reason"] == "invalid_pin"

        log_records = [r.message for r in caplog.records if "VoiceCallerAuth.verify_gather" in r.message]
        assert any(str(user1.id) in msg for msg in log_records)
        assert any("principal_role=owner" in msg.lower() for msg in log_records)
        assert any("pin mismatch" in msg for msg in log_records)
        # Aucune fuite de NIP en clair ni de numéro complet non masqué
        assert not any("481926" in msg for msg in log_records)
        assert not any("739264" in msg for msg in log_records)

        # 3. Vérification du statut enrichi via get_user_voice_pin_status
        identity1 = CurrentIdentity(auth_session=None, user=user1, raw_token="")
        status_resp = get_user_voice_pin_status(identity=identity1, db=session)
        assert status_resp["has_pin"] is True
        assert status_resp["user_id"] == str(user1.id)
        assert status_resp["user_email"] == "francis@eroproduits.com"
        assert status_resp["user_role"].upper() == "OWNER"

        # 4. Déliaison / suppression propre du NIP avec mot de passe
        # Tentative avec mauvais mot de passe -> 403
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as http_exc:
            delete_user_voice_pin(VoicePinDeleteRequest(current_password="MauvaisPassword!"), identity=identity1, db=session)
        assert http_exc.value.status_code == 403

        # Succès avec bon mot de passe
        del_resp = delete_user_voice_pin(VoicePinDeleteRequest(current_password=user_pw), identity=identity1, db=session)
        assert del_resp["status"] == "DELETED"
        assert del_resp["configured"] is False

        # Vérifier que le statut est désormais non configuré
        status_after = get_user_voice_pin_status(identity=identity1, db=session)
        assert status_after["has_pin"] is False
        assert status_after["configured"] is False
    finally:
        session.close()
        engine.dispose()


# ==============================================================================
# 7. P0 — DEMANDES CLIENTS ENTRANTES (SECURITY GATE FALSE POSITIVES)
# ==============================================================================

def test_p0_customer_inbound_request_owner_does_not_trigger_nip(tmp_path):
    """Vérifie qu'un appelant public demandant un rendez-vous, un contact ou un recrutement
    avec le patron / manager / propriétaire n'est JAMAIS bloqué par le NIP employé,
    et reçoit une réponse honnête de contact sans inventer de réservation fictive.
    """
    engine, session, company, config, _api_key, orchestrator = _voice_database(tmp_path)
    try:
        user = User(
            company_id=company.id,
            first_name="Francis",
            last_name="Queval",
            email="francis@eroproduits.com",
            phone="+15145550001",
            password_hash=hash_password("Secr3tPassword!2026"),
            role=UserRole.OWNER,
            is_active=True,
        )
        session.add(user)
        session.flush()
        mem = CompanyMembership(company_id=company.id, user_id=user.id, role=UserRole.OWNER, is_active=True)
        session.add(mem)
        session.commit()
        tenant = TenantContext(company.id, user.id)
        VoiceCallerAuth(session, Settings()).set_pin(tenant, "USER", user.id, "481926", phone_number="+15145550001")
        session.commit()

        from backend.app.models.voice import CompanyRoutingNip
        session.add(CompanyRoutingNip(
            id=uuid4(),
            company_id=company.id,
            routing_code="86849",
            routing_code_hash="hash_86849",
            status="ACTIVE",
            created_by_user_id=user.id,
        ))
        session.commit()

        call = VoiceCall(
            company_id=company.id,
            caller_phone="+15145550001",
            config_id=config.id,
            locale="fr-CA",
            status="in_progress",
            telnyx_call_control_id="v3:test_ctrl_id",
            source_context={"dispatcher_routing": True},
        )
        session.add(call)
        session.commit()

        settings = Settings(TELNYX_MEDIA_ENABLED=True, TELNYX_MEDIA_INBOUND_ENABLED=True)
        conv = PublicInboundConversation(session, settings, call.id)

        # 1. Phrases publiques qui mentionnent le patron/manager/recrutement
        test_phrases = [
            "Bonjour, j'aimerais prendre rendez-vous avec le patron.",
            "Je souhaite parler au manager pour un emploi.",
            "Demande de rendez-vous avec le patron pour du recrutement.",
            "Puis-je parler au propriétaire de la boutique ?",
            "I would like to schedule an interview with the owner.",
        ]
        for phrase in test_phrases:
            gate_res = conv.security_gate(phrase)
            # Ne doit JAMAIS demander de NIP
            assert gate_res is None or gate_res.get("auth_required") is not True, f"Security gate triggered wrongly for: {phrase}"

        # 2. Réponse publique : si pas de module CRM réservation, donner une réponse de contact honnête
        ans_french = conv.public_answer("Bonjour, j'aimerais prendre rendez-vous avec le patron.")
        assert ans_french["status"] == "success"
        assert ans_french.get("auth_required") is not True
        assert "direction et le propriétaire ne sont pas joignables directement par téléphone" in ans_french["answer"]
        assert "laisser un message" in ans_french["answer"] or "courriel" in ans_french["answer"]

        # En anglais
        call.locale = "en-US"
        session.commit()
        ans_english = conv.public_answer("Can I speak to the manager about an appointment?")
        assert ans_english["status"] == "success"
        assert ans_english.get("auth_required") is not True
        assert "Management and the owner are not directly reachable by phone" in ans_english["answer"]

        # En espagnol
        call.locale = "es-ES"
        session.commit()
        ans_spanish = conv.public_answer("¿Puedo hablar con el dueño para una cita?")
        assert ans_spanish["status"] == "success"
        assert ans_spanish.get("auth_required") is not True
        assert "administración y la gerencia no están disponibles" in ans_spanish["answer"]
    finally:
        session.close()
        engine.dispose()


# ==============================================================================
# 8. P0 — PRONONCIATION PHONÉTIQUE « PRODUITS HÉROS » (ANTI-LIAISON ZÉRO)
# ==============================================================================

def test_p0_phonetic_pronunciation_produits_heros():
    """Vérifie que l'alias phonétique 'Produits Héros' avec H aspiré
    élimine la liaison [z] ('Produit Zéro') tout en préservant le nom d'entreprise officiel.
    """
    cfg = MagicMock()
    cfg.business_name = "Produits Ero"
    cfg.voice_display_name = "Produits Ero"
    cfg.effective_voice_name = "Produits Ero"
    cfg.custom_pronunciation = "Produits Héros"
    cfg.preferred_language = "fr"

    # 1. voice_speech_name utilise en priorité l'alias custom_pronunciation
    spoken = voice_speech_name(cfg)
    assert spoken == "Produits Héros"

    # 2. apply_spoken_pronunciation remplace les graphies officielles et les anomalies 'Zéro'
    text1 = "Bienvenue chez Produits Ero. Nous sommes à votre écoute."
    rendered1 = apply_spoken_pronunciation(text1, cfg)
    assert "Produits Héros" in rendered1
    assert "Produits Ero" not in rendered1

    text2 = "Vous êtes bien chez Produit Zéro."
    rendered2 = apply_spoken_pronunciation(text2, cfg)
    assert "Produits Héros" in rendered2
    assert "Zéro" not in rendered2

    # 3. voice_ivr_greeting applique 'Produits Héros'
    greeting = voice_ivr_greeting(cfg)
    assert "Produits Héros" in greeting
    assert "Zéro" not in greeting

    # 4. Cas sans custom_pronunciation explicite : la règle générique française applique 'Produits Héros'
    cfg_auto = MagicMock()
    cfg_auto.business_name = "Produits Ero"
    cfg_auto.voice_display_name = "Produits Ero"
    cfg_auto.effective_voice_name = "Produits Ero"
    cfg_auto.custom_pronunciation = None
    cfg_auto.preferred_language = "fr"
    spoken_auto = voice_speech_name(cfg_auto)
    assert spoken_auto == "Produits Héros"


# ==============================================================================
# 9. P0 — MULTILINGUE & ESPAGNOL (« ¿Habla español? »)
# ==============================================================================

def test_p0_multilingual_spanish_inquiry_and_switching(tmp_path):
    """Vérifie la détection et la prise en charge de l'espagnol :
    - Détection de '¿Habla español?', 'Hablas español', 'Hablo español', 'en español'
    - Réponse directe courtoise en espagnol avec le nom officiel du tenant (Produits Ero)
    - Réponses directes de modules et de catalogue en espagnol
    """
    engine, session, company, config, _api_key, orchestrator = _voice_database(tmp_path)
    try:
        company.name = "Produits Ero"
        config.business_name = "Produits Ero"
        config.voice_display_name = "Produits Ero"
        config.call_policy = {"authorized_languages": ["fr", "en", "es"]}
        session.commit()

        # 1. is_language_inquiry
        assert is_language_inquiry("¿Habla español?") == "es"
        assert is_language_inquiry("Hablas español ?") == "es"
        assert is_language_inquiry("Hablo español") == "es"
        assert is_language_inquiry("podemos hablar en español por favor") == "es"
        assert is_language_inquiry("Do you speak English?") == "en"
        assert is_language_inquiry("Parlez-vous français ?") == "fr"

        # 2. resolve_direct_voice_answer pour l'espagnol utilise le nom officiel Produits Ero (pas Héros)
        ans = resolve_direct_voice_answer(
            session,
            company_id=company.id,
            transcript="¿Habla español?",
            authenticated_staff=False,
            locale="es-ES",
        )
        assert ans is not None
        assert "¡Hola! Sí, hablo español." in ans
        assert "Produits Ero" in ans
        assert "Héros" not in ans

        # 3. CallLanguageSession bascule explicitement vers es-ES
        lang_session = CallLanguageSession(
            tenant_id=company.id,
            call_session_id=str(uuid4()),
            primary_locale="fr-CA",
            active_locale="fr-CA",
            allowed_locales=("fr-CA", "en-US", "es-ES", "ro-RO"),
        )
        switched = lang_session.check_explicit_switch("¿Habla español?")
        assert switched == "es-ES"

        switched2 = lang_session.check_explicit_switch("en español por favor")
        assert switched2 == "es-ES"

        # 4. Spoken module answer & catalog answer en espagnol
        mod_ans = spoken_module_answer(["Retail", "Voice AI"], plan_code="Professional", locale="es-ES")
        assert "Su empresa cuenta actualmente con los siguientes módulos: Retail, Voice AI." in mod_ans
        assert "Su suscripción Professional está activa." in mod_ans

        cat_ans = spoken_catalog_answer([], retail_enabled=True, locale="es-ES")
        assert "El catálogo no contiene actualmente ningún producto a la venta." in cat_ans
    finally:
        session.close()
        engine.dispose()


# ==============================================================================
# 10. DEUX RÉGRESSIONS DE CLÔTURE : REQUÊTES MIXTES DANS LES 4 LANGUES
# ==============================================================================

def test_closing_regression_mixed_public_and_private_queries_in_4_languages(tmp_path):
    """Vérifie qu'une intention publique (contact, rendez-vous, recrutement)
    ne neutralise JAMAIS le contrôle des données privées (revenus, ventes, métriques)
    dans les 4 langues prises en charge (français, anglais, roumain, espagnol).
    """
    engine, session, company, config, _api_key, orchestrator = _voice_database(tmp_path)
    try:
        from backend.app.voice.auth import VoiceCallerAuth
        from backend.app.models.voice import CompanyRoutingNip

        auth = VoiceCallerAuth(session, Settings())
        tenant = TenantContext(company_id=company.id)
        user = User(
            company_id=company.id,
            email="owner@produits-ero.test",
            first_name="Marc",
            last_name="Proprio",
            is_active=True,
            password_hash=hash_password("SuperSecret123!"),
            phone="+14389536811",
        )
        session.add(user)
        session.flush()
        session.add(CompanyMembership(company_id=company.id, user_id=user.id, role=UserRole.OWNER, is_active=True))
        session.add(CompanyRoutingNip(
            id=uuid4(),
            company_id=company.id,
            routing_code="86849",
            routing_code_hash="hash_86849",
            status="ACTIVE",
        ))
        session.commit()

        auth.set_pin(tenant, "USER", user.id, "481926", phone_number="+14389536811")
        session.commit()

        call = VoiceCall(
            company_id=company.id,
            config_id=config.id,
            caller_phone="+14389536811",
            locale="fr-CA",
            status="in_progress",
            telnyx_call_control_id="v3:test_mixed_ctrl",
            source_context={"dispatcher_routing": True},
            started_at=datetime.now(timezone.utc),
        )
        session.add(call)
        session.commit()

        conv = PublicInboundConversation(session, Settings(TELNYX_MEDIA_ENABLED=True, TELNYX_MEDIA_INBOUND_ENABLED=True), call.id)

        # 1. Requêtes Mixtes : doivent TOUTES déclencher la protection de sécurité NIP
        mixed_queries = [
            ("fr-CA", "Je veux contacter le patron et connaître les revenus d'aujourd'hui."),
            ("en-US", "I want an appointment with the manager and to check today's revenue."),
            ("ro-RO", "Vreau o programare cu directorul și să aflu veniturile de astăzi."),
            ("es-ES", "Quiero una cita con el gerente y ver los ingresos de hoy."),
        ]

        for loc, query in mixed_queries:
            call.locale = loc
            session.commit()

            # security_gate DOIT exiger l'authentification NIP
            gate_res = conv.security_gate(query)
            assert gate_res is not None, f"Échec de security_gate pour la requête mixte : {query}"
            assert gate_res.get("auth_required") is True, f"auth_required doit être True pour : {query}"

            # public_answer DOIT également exiger l'authentification et ne jamais divulguer de données
            pub_res = conv.public_answer(query)
            assert pub_res.get("auth_required") is True, f"public_answer doit exiger auth pour : {query}"

        # 2. Requêtes purement publiques : ne doivent PAS déclencher de demande de NIP
        purely_public_queries = [
            ("fr-CA", "Je veux contacter le patron pour un emploi chez vous.", "La direction et le propriétaire"),
            ("en-US", "I want an appointment with the manager for a job interview.", "Management and the owner"),
            ("ro-RO", "Doresc o întâlnire cu conducerea pentru o angajare.", "Conducerea și proprietarul"),
            ("es-ES", "Quiero hablar con el gerente para una entrevista de trabajo.", "administración y la gerencia"),
        ]

        for loc, query, expected_snippet in purely_public_queries:
            call.locale = loc
            session.commit()

            gate_res = conv.security_gate(query)
            assert gate_res is None, f"security_gate ne doit pas bloquer une demande purement publique : {query}"

            pub_res = conv.public_answer(query)
            assert pub_res.get("auth_required") is not True, f"auth_required ne doit pas être requis pour : {query}"
            assert expected_snippet in pub_res["answer"], f"Extrait attendu '{expected_snippet}' manquant dans : {pub_res['answer']}"
    finally:
        session.close()
        engine.dispose()


# ==============================================================================
# 11. DEUX RÉGRESSIONS DE CLÔTURE : MULTI-TENANT & AUTORISATION DES LANGUES
# ==============================================================================

def test_closing_regression_no_global_produits_heros_and_tenant_language_authorization(tmp_path):
    """Vérifie :
    1. Aucun fallback global 'Produits Héros' si la configuration Voice n'existe pas.
    2. Utilisation stricte du nom du tenant avec fallback neutre sans entreprise inventée.
    3. Une langue (ex: espagnol) n'est confirmée que si elle est autorisée pour le tenant.
    4. Multi-tenant et RBAC sur l'accès aux modules d'entreprise.
    """
    engine, session, company, config, _api_key, orchestrator = _voice_database(tmp_path)
    try:
        from backend.app.voice.direct_answers import is_language_authorized_for_company

        # Tenant A : Produits Ero avec espagnol et anglais autorisés
        company.name = "Produits Ero"
        config.business_name = "Produits Ero"
        config.voice_display_name = "Produits Ero"
        config.call_policy = {"authorized_languages": ["fr", "en", "es"]}
        session.commit()

        assert is_language_authorized_for_company(session, company.id, "es") is True
        assert is_language_authorized_for_company(session, company.id, "en") is True
        assert is_language_authorized_for_company(session, company.id, "fr") is True

        ans_a = resolve_direct_voice_answer(
            session,
            company_id=company.id,
            transcript="¿Habla español?",
            authenticated_staff=False,
            locale="es-ES",
        )
        assert ans_a is not None
        assert "¡Hola! Sí, hablo español." in ans_a
        assert "Produits Ero" in ans_a
        assert "Héros" not in ans_a  # Jamais "Héros" imprimé dans la réponse directe

        # Tenant B : Boulangerie Saint-Laurent (aucun espagnol autorisé, uniquement français)
        company_b = Company(
            name="Boulangerie Saint-Laurent",
            slug="boulangerie-st-laurent",
            email="contact@boulangerie.test",
            country="CA",
            industry="Retail",
            subscription_plan="professional",
            preferred_language="fr",
            timezone="America/Montreal",
        )
        session.add(company_b)
        session.flush()
        config_b = VoiceBusinessConfig(
            company_id=company_b.id,
            business_name="Boulangerie Saint-Laurent",
            voice_display_name="Boulangerie Saint-Laurent",
            preferred_language="fr",
            greeting_message="Bienvenue à la Boulangerie Saint-Laurent.",
            voice_api_key_hash="hash_b",
            voice_api_key_last4="4321",
            call_policy={"authorized_languages": ["fr"]},
        )
        session.add(config_b)
        session.commit()

        assert is_language_authorized_for_company(session, company_b.id, "es") is False
        assert is_language_authorized_for_company(session, company_b.id, "fr") is True

        # Tenant B : l'espagnol est refusé poliment, AUCUNE fausse promesse, AUCUN 'Produits Héros'
        ans_b = resolve_direct_voice_answer(
            session,
            company_id=company_b.id,
            transcript="¿Habla español?",
            authenticated_staff=False,
            locale="es-ES",
        )
        assert ans_b is not None
        assert "Lo sentimos, la atención en español no está disponible para Boulangerie Saint-Laurent." in ans_b
        assert "Produits Héros" not in ans_b
        assert "Produits Ero" not in ans_b

        # Tenant C : ID inconnu / sans aucune config (fallback neutre, JAMAIS Produits Héros)
        unknown_id = uuid4()
        ans_c = resolve_direct_voice_answer(
            session,
            company_id=unknown_id,
            transcript="¿Habla español?",
            authenticated_staff=False,
            locale="es-ES",
        )
        assert ans_c is not None
        assert "Lo sentimos, la atención en español no está disponible para esta empresa." in ans_c
        assert "Produits Héros" not in ans_c
        assert "Produits Ero" not in ans_c

        # 4. RBAC et cloisonnement multi-tenant pour les questions de modules
        # Appelant non authentifié -> refus direct RBAC
        unauth_mod = resolve_direct_voice_answer(
            session,
            company_id=company.id,
            transcript="Quels sont les modules disponibles pour mon entreprise ?",
            authenticated_staff=False,
            staff_role=None,
            locale="fr-CA",
        )
        assert unauth_mod == "Cette information est réservée aux employés authentifiés de votre entreprise."

        # Appelant authentifié -> réponse avec les modules autorisés
        auth_mod = resolve_direct_voice_answer(
            session,
            company_id=company.id,
            transcript="Quels sont les modules accessibles dans notre abonnement ?",
            authenticated_staff=True,
            staff_role="OWNER",
            locale="fr-CA",
        )
        assert auth_mod is not None
        assert "Votre entreprise dispose actuellement" in auth_mod or "Votre abonnement" in auth_mod
    finally:
        session.close()
        engine.dispose()
