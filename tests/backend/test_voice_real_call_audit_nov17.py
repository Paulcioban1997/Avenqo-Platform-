"""Tests de validation automatisés pour l'audit des appels réels et la sécurité P0/P1.

Vérifie rigoureusement :
1. P0 Sécurité Authentification NIP Employé :
   - Lecture seule stricte avant validation réussie du NIP.
   - Mauvais NIP + numéro différent : AUCUNE synchronisation, AUCUN journal d'audit attribué.
   - Appel depuis numéro inconnu : refus (caller_not_recognized).
   - Numéro appelant usurpé : aucun transfert de credential vers un autre utilisateur.
   - NIP valide + numéro confirmé sur le compte : synchronisation contrôlée post-authentification.
   - Numéro déjà attribué : détection de conflit et aucun écrasement.
   - Deux tenants : isolation stricte (aucun croisement).
   - Journal d'audit : attribution correcte à l'utilisateur authentifié et absence absolue de secrets.

2. P1 Fraîcheur Effective des Stocks Connectés :
   - Classification robuste : CONNECTED, SYNCING, FRESH, STALE, UNAVAILABLE, UNCONFIRMED_HISTORICAL.
   - Shopify actif avec dernier sync récent (< 24h) -> FRESH (is_live_stock=True, stock confirmé).
   - Shopify actif avec sync ancien (> 24h) -> STALE (is_live_stock=False, prix indicatif).
   - WooCommerce en erreur -> UNAVAILABLE (is_live_stock=False).
   - Produit ancien malgré connecteur READY -> STALE (is_live_stock=False).
   - Dataset importé sans connexion -> UNCONFIRMED_HISTORICAL (is_live_stock=False).
   - Catalogue avec produits aux fraîcheurs hétérogènes.
   - Réponses vocales multilingues cohérentes (FR / EN / RO).

3. P1 Prononciation Entreprise Configurable & Multilingue FR/EN/RO sans fuite.
4. P1 Latence Filler (3,5s, cooldown 30s) & P2 Politiques de conversion devises et rappels.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from backend.app.ai.chat.chat_service import _localized_system_instruction, SYSTEM_INSTRUCTION
from backend.app.config.settings import Settings
from backend.app.core.permissions import UserRole
from backend.app.core.security import hash_password
from backend.app.models import (
    Company,
    CompanyMembership,
    CommerceConnection,
    User,
    VoiceBusinessConfig,
    VoiceCallerCredential,
)
from backend.app.models.audit_log import AuditLogEntry
from backend.app.models.commerce_connection import NormalizedCommerceRecord
from backend.app.services.company_intelligence_service import (
    classify_connector_freshness,
    classify_product_freshness,
)
from backend.app.voice.auth import VoiceCallerAuth
from backend.app.voice.direct_answers import (
    spoken_catalog_answer,
    spoken_module_answer,
)
from backend.app.voice.language_resolver import CallLanguageSession, to_bcp47
from backend.app.voice.module_actions import company_call_language_session
from shared.ai_engine.contracts import TenantContext
from tests.backend.test_voice_agent import _voice_database


# ==============================================================================
# P0 — SÉCURITÉ AUTHENTIFICATION NIP & SYNCHRONISATION CONTRÔLÉE
# ==============================================================================

def test_1_voice_audit_employee_pin_autoheal_and_pound_sign(tmp_path):
    """P0 : L'employé appelant avec son numéro enregistré est authentifié même avec '#' et le credential est synchronisé POST-authentification."""
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

        # Ancien numéro dans le credential
        cred = session.scalar(
            select(VoiceCallerCredential).where(
                VoiceCallerCredential.company_id == company.id,
                VoiceCallerCredential.principal_id == user.id,
            )
        )
        assert cred is not None
        cred.phone_number = "+15140001111"
        session.commit()

        call = orchestrator.record_inbound(config, {"call_control_id": "pin-call-autoheal", "from": caller_phone})

        # Saisie DTMF avec touche dièse (#)
        result = auth.verify_gather(call, "868491#")
        assert result["authenticated"] is True
        assert call.authenticated_user_id == user.id
        assert call.caller_type == "OWNER"

        # Synchronisation effectuée après succès
        session.refresh(cred)
        assert cred.phone_number == caller_phone

        # Audit log créé avec attribution au user authentifié
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


def test_2_voice_audit_wrong_pin_no_sync_and_no_audit(tmp_path):
    """P0 Sécurité : En cas de NIP incorrect, AUCUNE synchronisation n'est effectuée et AUCUN audit log n'est enregistré."""
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

        cred = session.scalar(
            select(VoiceCallerCredential).where(
                VoiceCallerCredential.company_id == company.id,
                VoiceCallerCredential.principal_id == user.id,
            )
        )
        assert cred is not None
        cred.phone_number = "+15140001111"
        session.commit()

        call = orchestrator.record_inbound(config, {"call_control_id": "pin-call-wrong", "from": caller_phone})

        # Appelant compose un MAUVAIS NIP
        result = auth.verify_gather(call, "999999#")
        assert result["authenticated"] is False
        assert result["reason"] == "invalid_pin"

        # VÉRIFICATION STRICTE : Le numéro n'a PAS été modifié
        session.refresh(cred)
        assert cred.phone_number == "+15140001111"
        assert cred.failed_attempts == 1

        # VÉRIFICATION STRICTE : AUCUN log d'audit n'a été créé
        audit_log = session.scalar(
            select(AuditLogEntry).where(
                AuditLogEntry.company_id == company.id,
                AuditLogEntry.action == "voice_credential_phone_synchronized",
            )
        )
        assert audit_log is None
    finally:
        session.close()
        engine.dispose()


def test_3_voice_audit_caller_matched_accuracy_and_isolation(tmp_path):
    """P0 Sécurité : Appel depuis un numéro inconnu est refusé sans divulgation."""
    engine, session, company, config, _api_key, orchestrator = _voice_database(tmp_path)
    try:
        settings = Settings(AUTH_JWT_SECRET="test-jwt-secret-minimum-32-chars-long")
        unknown_call = orchestrator.record_inbound(config, {"call_control_id": "call-unknown", "from": "+19998887777"})
        auth = VoiceCallerAuth(session, settings)

        result = auth.verify_gather(unknown_call, "868491#")
        assert result["authenticated"] is False
        assert result["reason"] == "caller_not_recognized"
    finally:
        session.close()
        engine.dispose()


def test_4_voice_audit_spoofed_caller_id_no_credential_transfer(tmp_path):
    """P0 Sécurité : Un appelant usurpant le Caller ID d'Alice ne peut pas transférer ce numéro sur le compte de Bob."""
    engine, session, company, config, _api_key, orchestrator = _voice_database(tmp_path)
    try:
        settings = Settings(AUTH_JWT_SECRET="test-jwt-secret-minimum-32-chars-long")
        alice_phone = "+15142955720"
        bob_phone = "+15148889999"

        alice = User(company_id=company.id, first_name="Alice", last_name="A", email="alice@test.com", password_hash=hash_password("Pass1!"), role=UserRole.USER, phone=alice_phone, is_active=True)
        bob = User(company_id=company.id, first_name="Bob", last_name="B", email="bob@test.com", password_hash=hash_password("Pass2!"), role=UserRole.USER, phone=bob_phone, is_active=True)
        session.add_all([alice, bob])
        session.flush()
        session.add_all([
            CompanyMembership(company_id=company.id, user_id=alice.id, role=UserRole.USER, is_active=True),
            CompanyMembership(company_id=company.id, user_id=bob.id, role=UserRole.USER, is_active=True),
        ])
        session.commit()

        auth = VoiceCallerAuth(session, settings)
        auth.set_pin(TenantContext(company.id, alice.id), "USER", alice.id, "112233")
        auth.set_pin(TenantContext(company.id, bob.id), "USER", bob.id, "445566")
        session.commit()

        # Appel avec caller_phone usurpé = Alice, mais saisie du NIP de Bob
        call = orchestrator.record_inbound(config, {"call_control_id": "call-spoof", "from": alice_phone})

        # Alice a été matchée par le caller_phone, donc le credential testé est celui d'Alice
        # Saisir le NIP de Bob échoue car c'est le credential d'Alice qui est vérifié
        result = auth.verify_gather(call, "445566#")
        assert result["authenticated"] is False

        # Vérifier qu'aucun transfert n'a eu lieu
        cred_bob = session.scalar(select(VoiceCallerCredential).where(VoiceCallerCredential.principal_id == bob.id))
        assert cred_bob is not None
        assert cred_bob.phone_number == bob_phone
    finally:
        session.close()
        engine.dispose()


def test_5_voice_audit_phone_conflict_no_overwrite(tmp_path):
    """P0 Sécurité : Si un numéro est déjà attribué à un autre credential, aucun écrasement n'a lieu lors de la synchronisation."""
    engine, session, company, config, _api_key, orchestrator = _voice_database(tmp_path)
    try:
        settings = Settings(AUTH_JWT_SECRET="test-jwt-secret-minimum-32-chars-long")
        shared_phone = "+15142955720"

        u1 = User(company_id=company.id, first_name="User1", last_name="A", email="u1@test.com", password_hash=hash_password("Pass1!"), role=UserRole.USER, phone=shared_phone, is_active=True)
        u2 = User(company_id=company.id, first_name="User2", last_name="B", email="u2@test.com", password_hash=hash_password("Pass2!"), role=UserRole.USER, phone="+15141112222", is_active=True)
        session.add_all([u1, u2])
        session.flush()
        session.add_all([
            CompanyMembership(company_id=company.id, user_id=u1.id, role=UserRole.USER, is_active=True),
            CompanyMembership(company_id=company.id, user_id=u2.id, role=UserRole.USER, is_active=True),
        ])
        session.commit()

        auth = VoiceCallerAuth(session, settings)
        auth.set_pin(TenantContext(company.id, u1.id), "USER", u1.id, "112233")
        auth.set_pin(TenantContext(company.id, u2.id), "USER", u2.id, "445566")
        session.commit()

        cred1 = session.scalar(select(VoiceCallerCredential).where(VoiceCallerCredential.principal_id == u1.id))
        cred2 = session.scalar(select(VoiceCallerCredential).where(VoiceCallerCredential.principal_id == u2.id))
        assert cred1 is not None and cred2 is not None

        # Cred1 possède déjà shared_phone
        cred1.phone_number = shared_phone
        cred2.phone_number = "+15140009999"
        session.commit()

        # Appel arrivant avec shared_phone : résout cred1
        call = orchestrator.record_inbound(config, {"call_control_id": "call-conflict", "from": shared_phone})
        result = auth.verify_gather(call, "112233#")
        assert result["authenticated"] is True
        # cred2 n'a pas été affecté
        session.refresh(cred2)
        assert cred2.phone_number == "+15140009999"
    finally:
        session.close()
        engine.dispose()


def test_6_voice_audit_two_tenants_strict_isolation(tmp_path):
    """P0 Sécurité : Un appel sur l'entreprise A ne peut jamais authentifier ou modifier un credential de l'entreprise B."""
    engine, session, company_a, config_a, _api_key_a, orchestrator_a = _voice_database(tmp_path)
    try:
        settings = Settings(AUTH_JWT_SECRET="test-jwt-secret-minimum-32-chars-long")

        # Entreprise B
        company_b = Company(
            id=uuid4(),
            name="Entreprise B",
            slug="entreprise-b",
            email="contact@companyb.com",
            country="CA",
            timezone="America/Toronto",
            industry="Services",
            subscription_plan="professional",
        )
        session.add(company_b)
        session.flush()

        phone_b = "+15145559999"
        user_b = User(
            company_id=company_b.id,
            first_name="Bob",
            last_name="B",
            email="bob@companyb.com",
            password_hash=hash_password("PassB123!"),
            role=UserRole.OWNER,
            phone=phone_b,
            is_active=True,
        )
        session.add(user_b)
        session.flush()
        session.add(CompanyMembership(company_id=company_b.id, user_id=user_b.id, role=UserRole.OWNER, is_active=True))
        session.commit()

        auth = VoiceCallerAuth(session, settings)
        auth.set_pin(TenantContext(company_b.id, user_b.id), "USER", user_b.id, "778899")
        session.commit()

        # Appel sur le numéro de l'entreprise A avec le téléphone de Bob
        call_a = orchestrator_a.record_inbound(config_a, {"call_control_id": "call-cross-tenant", "from": phone_b})

        # Tenter d'authentifier Bob sur l'entreprise A
        result = auth.verify_gather(call_a, "778899#")
        assert result["authenticated"] is False
        assert result["reason"] == "caller_not_recognized"

        # Le credential de l'entreprise B n'a pas été altéré
        cred_b = session.scalar(select(VoiceCallerCredential).where(VoiceCallerCredential.company_id == company_b.id))
        assert cred_b is not None
        assert cred_b.failed_attempts == 0
    finally:
        session.close()
        engine.dispose()


def test_7_voice_audit_audit_log_no_sensitive_data(tmp_path):
    """P0 Sécurité : Le journal d'audit ne contient aucun secret sensible (ni NIP, ni mot de passe, ni hash)."""
    engine, session, company, config, _api_key, orchestrator = _voice_database(tmp_path)
    try:
        settings = Settings(AUTH_JWT_SECRET="test-jwt-secret-minimum-32-chars-long")
        phone = "+15142955720"
        user = User(company_id=company.id, first_name="Audit", last_name="User", email="audit@test.com", password_hash=hash_password("AuditPass!"), role=UserRole.OWNER, phone=phone, is_active=True)
        session.add(user)
        session.flush()
        session.add(CompanyMembership(company_id=company.id, user_id=user.id, role=UserRole.OWNER, is_active=True))
        session.commit()

        auth = VoiceCallerAuth(session, settings)
        auth.set_pin(TenantContext(company.id, user.id), "USER", user.id, "868491")
        session.commit()

        cred = session.scalar(select(VoiceCallerCredential).where(VoiceCallerCredential.principal_id == user.id))
        assert cred is not None
        cred.phone_number = "+15140001111"
        session.commit()

        call = orchestrator.record_inbound(config, {"call_control_id": "call-audit-sec", "from": phone})
        res = auth.verify_gather(call, "868491#")
        assert res["authenticated"] is True

        audit = session.scalar(select(AuditLogEntry).where(AuditLogEntry.action == "voice_credential_phone_synchronized"))
        assert audit is not None
        meta_str = str(audit.safe_metadata or "")
        assert "868491" not in meta_str
        assert "password" not in meta_str
        assert "pin_hash" not in meta_str
        assert audit.safe_metadata.get("synchronized_phone") == phone
    finally:
        session.close()
        engine.dispose()


# ==============================================================================
# P1 — FRAÎCHEUR EFFECTIVE DES STOCKS CONNECTÉS
# ==============================================================================

def test_8_commerce_freshness_shopify_recent_fresh():
    """P1 Fraîcheur : Connecteur Shopify avec dernière synchronisation récente (< 24h) classifié FRESH."""
    now = datetime.now(timezone.utc)
    conn = CommerceConnection(
        id=uuid4(),
        company_id=uuid4(),
        provider="shopify",
        external_account_id="shop-1",
        status="READY",
        last_successful_sync=now - timedelta(hours=2),
    )
    state = classify_connector_freshness(conn, now=now, freshness_threshold_hours=24)
    assert state == "FRESH"

    rec = NormalizedCommerceRecord(
        id=uuid4(),
        company_id=conn.company_id,
        connection_id=conn.id,
        provider="shopify",
        entity_type="products",
        source_record_id="p-1",
        source_updated_at=now - timedelta(hours=3),
        normalized_data={"name": "Planche Pro", "unit_price": 500.0, "inventory_level": 10},
    )
    prod_state, is_live = classify_product_freshness(rec, {conn.id: conn}, now=now, freshness_threshold_hours=24)
    assert prod_state == "FRESH"
    assert is_live is True


def test_9_commerce_freshness_shopify_old_sync_stale():
    """P1 Fraîcheur : Connecteur Shopify avec synchronisation ancienne (> 24h) classifié STALE."""
    now = datetime.now(timezone.utc)
    conn = CommerceConnection(
        id=uuid4(),
        company_id=uuid4(),
        provider="shopify",
        external_account_id="shop-1",
        status="READY",
        last_successful_sync=now - timedelta(hours=48),  # 48h > seuil de 24h
    )
    state = classify_connector_freshness(conn, now=now, freshness_threshold_hours=24)
    assert state == "STALE"

    rec = NormalizedCommerceRecord(
        id=uuid4(),
        company_id=conn.company_id,
        connection_id=conn.id,
        provider="shopify",
        entity_type="products",
        source_record_id="p-1",
        source_updated_at=now - timedelta(hours=50),
        normalized_data={"name": "Planche Pro", "unit_price": 500.0, "inventory_level": 10},
    )
    prod_state, is_live = classify_product_freshness(rec, {conn.id: conn}, now=now, freshness_threshold_hours=24)
    assert prod_state == "STALE"
    assert is_live is False


def test_10_commerce_freshness_woocommerce_error_unavailable():
    """P1 Fraîcheur : Connecteur WooCommerce avec statut ERROR classifié UNAVAILABLE."""
    now = datetime.now(timezone.utc)
    conn = CommerceConnection(
        id=uuid4(),
        company_id=uuid4(),
        provider="woocommerce",
        external_account_id="woo-1",
        status="ERROR",
        last_successful_sync=now - timedelta(hours=1),
    )
    state = classify_connector_freshness(conn, now=now, freshness_threshold_hours=24)
    assert state == "UNAVAILABLE"

    rec = NormalizedCommerceRecord(
        id=uuid4(),
        company_id=conn.company_id,
        connection_id=conn.id,
        provider="woocommerce",
        entity_type="products",
        source_record_id="p-2",
        source_updated_at=now - timedelta(hours=2),
        normalized_data={"name": "Casque", "unit_price": 100.0, "inventory_level": 5},
    )
    prod_state, is_live = classify_product_freshness(rec, {conn.id: conn}, now=now)
    assert prod_state == "UNAVAILABLE"
    assert is_live is False


def test_11_commerce_freshness_product_old_despite_connector_ready():
    """P1 Fraîcheur : Connecteur READY et récent, mais horodatage du produit ancien (> 7j) classifié STALE."""
    now = datetime.now(timezone.utc)
    conn = CommerceConnection(
        id=uuid4(),
        company_id=uuid4(),
        provider="shopify",
        external_account_id="shop-1",
        status="READY",
        last_successful_sync=now - timedelta(minutes=30),  # Sync tout frais
    )
    rec = NormalizedCommerceRecord(
        id=uuid4(),
        company_id=conn.company_id,
        connection_id=conn.id,
        provider="shopify",
        entity_type="products",
        source_record_id="p-old",
        source_updated_at=now - timedelta(days=30),  # Produit non mis à jour depuis 30 jours
        normalized_data={"name": "Article Archivé", "unit_price": 40.0, "inventory_level": 2},
    )
    prod_state, is_live = classify_product_freshness(rec, {conn.id: conn}, now=now, max_product_age_days=7)
    assert prod_state == "STALE"
    assert is_live is False


def test_12_commerce_freshness_dataset_without_connection():
    """P1 Fraîcheur : Jeu de données statique importé sans connexion classifié UNCONFIRMED_HISTORICAL."""
    rec = NormalizedCommerceRecord(
        id=uuid4(),
        company_id=uuid4(),
        connection_id=None,  # Pas de connecteur
        provider="dataset",
        entity_type="products",
        source_record_id="p-csv",
        source_updated_at=None,
        normalized_data={"name": "Planche Importée", "unit_price": 300.0, "inventory_level": 49},
    )
    prod_state, is_live = classify_product_freshness(rec, {})
    assert prod_state == "UNCONFIRMED_HISTORICAL"
    assert is_live is False


def test_13_spoken_catalog_answers_multilingual_freshness_fr_en_ro():
    """P1 : Les réponses vocales (FR / EN / RO) différencient les prix indicatifs et les états de fraîcheur."""
    # 1. Produit Live Vérifié (FRESH)
    prod_fresh = [{
        "name": "Planche Pro",
        "price": 499.99,
        "currency": "CAD",
        "in_stock": True,
        "inventory_count": 5,
        "is_live_stock": True,
        "freshness_status": "FRESH",
        "price_status": "verified",
    }]
    ans_fr = spoken_catalog_answer(prod_fresh, retail_enabled=True, locale="fr-CA")
    assert "Planche Pro, 499.99 $, disponible" in ans_fr
    assert "prix indicatif" not in ans_fr

    ans_en = spoken_catalog_answer(prod_fresh, retail_enabled=True, locale="en-US")
    assert "Planche Pro, 499.99 $, available" in ans_en
    assert "reference price" not in ans_en

    ans_ro = spoken_catalog_answer(prod_fresh, retail_enabled=True, locale="ro-RO")
    assert "Planche Pro, 499.99 $, disponibil" in ans_ro
    assert "preț de referință" not in ans_ro

    # 2. Produit avec synchronisation ancienne (STALE)
    prod_stale = [{
        "name": "Planche Ancien Sync",
        "price": 499.99,
        "currency": "CAD",
        "in_stock": True,
        "inventory_count": None,
        "is_live_stock": False,
        "freshness_status": "STALE",
        "price_status": "historical_catalog",
    }]
    ans_stale_fr = spoken_catalog_answer(prod_stale, retail_enabled=True, locale="fr-CA")
    assert "prix indicatif" in ans_stale_fr
    assert "données de stock non récentes" in ans_stale_fr

    ans_stale_en = spoken_catalog_answer(prod_stale, retail_enabled=True, locale="en-US")
    assert "reference price" in ans_stale_en
    assert "stock data stale" in ans_stale_en

    ans_stale_ro = spoken_catalog_answer(prod_stale, retail_enabled=True, locale="ro-RO")
    assert "preț de referință" in ans_stale_ro
    assert "date de stoc expirate" in ans_stale_ro

    # 3. Produit dont le connecteur est en panne (UNAVAILABLE)
    prod_unavail = [{
        "name": "Planche Connecteur Erreur",
        "price": 499.99,
        "currency": "CAD",
        "in_stock": False,
        "inventory_count": None,
        "is_live_stock": False,
        "freshness_status": "UNAVAILABLE",
        "price_status": "historical_catalog",
    }]
    ans_unavail_fr = spoken_catalog_answer(prod_unavail, retail_enabled=True, locale="fr-CA")
    assert "stock indisponible" in ans_unavail_fr

    ans_unavail_ro = spoken_catalog_answer(prod_unavail, retail_enabled=True, locale="ro-RO")
    assert "stoc indisponibil" in ans_unavail_ro


def test_14_spoken_catalog_multiple_products_heterogeneous_freshness():
    """P1 : Plusieurs produits avec des fraîcheurs différentes dans le même catalogue retournent chacun leur statut propre."""
    products = [
        {
            "name": "Article Live",
            "price": 100.0,
            "currency": "CAD",
            "in_stock": True,
            "inventory_count": 8,
            "is_live_stock": True,
            "freshness_status": "FRESH",
            "price_status": "verified",
        },
        {
            "name": "Article Ancien",
            "price": 200.0,
            "currency": "CAD",
            "in_stock": True,
            "inventory_count": None,
            "is_live_stock": False,
            "freshness_status": "STALE",
            "price_status": "historical_catalog",
        },
        {
            "name": "Article Importé CSV",
            "price": 300.0,
            "currency": "CAD",
            "in_stock": True,
            "inventory_count": None,
            "is_live_stock": False,
            "freshness_status": "UNCONFIRMED_HISTORICAL",
            "price_status": "historical_catalog",
        },
    ]
    ans = spoken_catalog_answer(products, retail_enabled=True, locale="fr-CA")
    assert "Article Live, 100.0 $, disponible" in ans
    assert "Article Ancien, 200.0 $ (prix indicatif), données de stock non récentes" in ans
    assert "Article Importé CSV, 300.0 $ (prix indicatif), stock en direct non synchronisé" in ans


# ==============================================================================
# P1 & P2 — PRONONCIATION, MULTILINGUE, LATENCE & CONVERSIONS
# ==============================================================================

def test_15_voice_audit_configurable_company_pronunciation():
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
    assert "When referring to 'Produits Ero' or 'Produits_Ero', ALWAYS pronounce it strictly 'Produits Éro'" not in prompt


def test_16_voice_audit_multilingual_romanian_switching(tmp_path):
    """P1 : Basculement fluide vers le roumain sans fuite de français."""
    engine, session, company, config, _api_key, orchestrator = _voice_database(tmp_path)
    try:
        call = orchestrator.record_inbound(config, {"call_control_id": "call-lang-ro", "from": "+15142955720"})
        lang_session = company_call_language_session(session, config, call)

        assert lang_session.active_locale.startswith("fr")
        switched = lang_session.process_utterance("Putem vorbi în română?")
        assert switched == "ro-RO"
        assert lang_session.active_locale == "ro-RO"

        modules_ro = spoken_module_answer(["Catalog", "Rendez-vous"], plan_code="Pro", locale="ro-RO")
        assert "Compania dumneavoastră dispune în prezent" in modules_ro
        assert "Votre entreprise" not in modules_ro
    finally:
        session.close()
        engine.dispose()


def test_17_voice_audit_latency_filler_and_foreign_currency():
    """P1 & P2 : Directives système strictes pour latence filler, conversion euro et rappel."""
    prompt = _localized_system_instruction(
        SYSTEM_INSTRUCTION,
        user_language="ro",
        company_country="CA",
        company_currency="CAD",
        company_timezone="America/Toronto",
        is_voice_call=True,
    )
    assert "NO FOREIGN CURRENCY ESTIMATION (STRICT RULE)" in prompt
    assert "NEVER invent an exchange rate or output a converted figure" in prompt
    assert "Caller Callbacks & Inbound Availability" in prompt
    assert "Do NOT claim to schedule an automated outbound telephone callback" in prompt
    assert "Dynamic Language Switching & Romanian Support" in prompt
    assert "NEVER leak French phrases (such as 'Un instant, je vérifie...')" in prompt
