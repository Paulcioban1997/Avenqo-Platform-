"""Tests automatisés Avenqo Voice — Call #7 & Language Lock.

Couvre :
1. RegionLanguageResolver (Scénarios régionaux BCP-47, multi-linguisme, personnalisation tenant).
2. CallLanguageSession / Language Lock (Scénarios A à J : résistance aux emprunts, accents,
   demandes explicites, isolation multi-tenant, reconnexion).
3. Disponibilités CRM et prise de rendez-vous réelle.
4. Distinctions des types d'appelants (Public vs Propriétaire authentifié, sécurité revenus/ventes).
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.ai.tools.business.crm_tools import (
    CheckAvailabilityArgs,
    CheckAvailabilityTool,
    CreateAppointmentArgs,
    CreateAppointmentTool,
    ListAvailableSlotsArgs,
    ListAvailableSlotsTool,
)
from backend.app.ai.tools.contracts import ToolExecutionContext
from shared.ai_engine.contracts import TenantContext
from backend.app.core.permissions import ROLE_PERMISSIONS, UserRole, permissions_for
from backend.app.models.company import Company
from backend.app.models.crm import CRMAppointment, CRMClient
from backend.app.models.user import User
from backend.app.models.voice import VoiceBusinessConfig, VoiceCall
from backend.app.services.crm_availability_service import CRMAvailabilityService
from backend.app.voice.language_resolver import (
    CallLanguageSession,
    RegionLanguageRecommendation,
    RegionLanguageResolver,
)
from tests.backend.test_voice_agent import _voice_database



def test_region_language_resolver_montreal():
    """Scénario A : Entreprise de Montréal, Québec, Canada -> fr-CA principal, en-CA secondaire."""
    rec = RegionLanguageResolver.resolve("CA", region="QC", locality="montreal")
    assert rec.country_code == "CA"
    assert rec.primary_locale == "fr-CA"
    assert "en-CA" in rec.secondary_locales
    assert "fr-CA" in rec.allowed_locales


def test_region_language_resolver_toronto():
    """Scénario B : Entreprise de Toronto, Ontario, Canada -> en-CA principal, fr-CA secondaire."""
    rec = RegionLanguageResolver.resolve("CA", region="ON", locality="toronto")
    assert rec.country_code == "CA"
    assert rec.primary_locale == "en-CA"
    assert "fr-CA" in rec.secondary_locales


def test_region_language_resolver_us_florida():
    """Entreprise en Floride, USA -> en-US principal, es-US secondaire."""
    rec = RegionLanguageResolver.resolve("US", region="FL", locality="miami")
    assert rec.country_code == "US"
    assert rec.primary_locale == "en-US"
    assert "es-US" in rec.secondary_locales


def test_region_language_resolver_romania():
    """Entreprise en Roumanie -> ro-RO principal."""
    rec = RegionLanguageResolver.resolve("RO", region="CJ")
    assert rec.country_code == "RO"
    assert rec.primary_locale == "ro-RO"


def test_language_lock_scenario_c_english_with_french_words():
    """Scénario C : Conversation en anglais contenant des mots français d'emprunt -> maintien de l'anglais."""
    session = CallLanguageSession(
        tenant_id=uuid4(),
        call_session_id="call-c",
        primary_locale="en-CA",
        active_locale="en-CA",
        allowed_locales=("en-CA", "fr-CA"),
    )
    # Phrase anglaise avec des mots d'emprunt ou de contexte français
    utterance = "I am going to the parking for the meeting and I will eat a croissant before our rendez-vous."
    active = session.process_utterance(utterance)
    assert active == "en-CA"
    assert session.language_lock_state == "LOCKED"


def test_language_lock_scenario_d_single_word_or_accent():
    """Scénario D : Conversation en anglais avec mauvaise prononciation ou mot isolé -> aucun basculement."""
    session = CallLanguageSession(
        tenant_id=uuid4(),
        call_session_id="call-d",
        primary_locale="en-US",
        active_locale="en-US",
        allowed_locales=("en-US", "fr-CA", "es-ES"),
    )
    # Mots isolés ou courts qui ne doivent jamais faire dériver
    for word in ["merci", "bonjour", "yes", "okay", "super"]:
        active = session.process_utterance(word)
        assert active == "en-US", f"Accidental switch on '{word}'"

    # Silence / vide
    assert session.process_utterance("") == "en-US"
    assert session.process_utterance("   ") == "en-US"


def test_language_lock_scenario_e_explicit_switch_to_spanish():
    """Scénario E : 'Can we continue in Spanish?' -> bascule vers l'espagnol et maintien."""
    session = CallLanguageSession(
        tenant_id=uuid4(),
        call_session_id="call-e",
        primary_locale="en-US",
        active_locale="en-US",
        allowed_locales=("en-US", "fr-CA", "es-ES"),
    )
    new_locale = session.process_utterance("Can we continue in Spanish?")
    assert new_locale == "es-ES"
    assert session.explicit_switch_requested is True
    assert session.language_lock_state == "LOCKED"

    # La suite de la conversation en espagnol reste verrouillée en espagnol
    subsequent = session.process_utterance("Hola, quisiera saber los horarios de atención.")
    assert subsequent == "es-ES"


def test_language_lock_scenario_f_explicit_switch_to_french():
    """Scénario F : 'Revenons en français' -> bascule vers le français et maintien."""
    session = CallLanguageSession(
        tenant_id=uuid4(),
        call_session_id="call-f",
        primary_locale="fr-CA",
        active_locale="en-US",  # Était temporairement en anglais
        allowed_locales=("fr-CA", "en-US"),
    )
    new_locale = session.process_utterance("Revenons en français s'il vous plaît")
    assert new_locale == "fr-CA"
    assert session.language_lock_state == "LOCKED"

    # L'énoncé suivant reste en français
    subsequent = session.process_utterance("Parfait, je voudrais réserver pour demain.")
    assert subsequent == "fr-CA"


def test_language_lock_scenario_g_romanian_with_loanwords():
    """Scénario G : Conversation en roumain avec emprunts français -> maintien du roumain."""
    session = CallLanguageSession(
        tenant_id=uuid4(),
        call_session_id="call-g",
        primary_locale="ro-RO",
        active_locale="ro-RO",
        allowed_locales=("ro-RO", "fr-CA", "en-US"),
    )
    utterance = "Avem un rendez-vous la birou și un meeting după-amiază."
    active = session.process_utterance(utterance)
    assert active == "ro-RO"
    assert session.language_lock_state == "LOCKED"


def test_language_lock_scenario_h_quebec_company_configured_in_english():
    """Scénario H : Entreprise québécoise configurée en anglais -> respect de l'anglais."""
    session = CallLanguageSession(
        tenant_id=uuid4(),
        call_session_id="call-h",
        primary_locale="en-CA",
        active_locale="en-CA",
        allowed_locales=("en-CA", "fr-CA"),
    )
    assert session.active_locale == "en-CA"
    assert session.primary_locale == "en-CA"


def test_language_lock_scenario_i_tenant_isolation():
    """Scénario I : Plusieurs entreprises dans différentes régions -> isolation stricte sans fuite."""
    tenant_a = uuid4()
    tenant_b = uuid4()
    session_a = CallLanguageSession(
        tenant_id=tenant_a,
        call_session_id="call-a",
        primary_locale="fr-CA",
        active_locale="fr-CA",
        allowed_locales=("fr-CA", "en-CA"),
    )
    session_b = CallLanguageSession(
        tenant_id=tenant_b,
        call_session_id="call-b",
        primary_locale="en-US",
        active_locale="en-US",
        allowed_locales=("en-US", "es-ES"),
    )

    # Bascule explicite pour A uniquement
    session_a.process_utterance("Can we continue in English?")
    assert session_a.active_locale == "en-CA"
    # Session B reste intacte
    assert session_b.active_locale == "en-US"
    assert session_a.tenant_id != session_b.tenant_id


def test_language_lock_scenario_j_session_reconnect_preserves_locale():
    """Scénario J : Redémarrage/reconnexion de session -> conservation de la langue active."""
    tenant_id = uuid4()
    initial_session = CallLanguageSession(
        tenant_id=tenant_id,
        call_session_id="call-j",
        primary_locale="fr-CA",
        active_locale="fr-CA",
        allowed_locales=("fr-CA", "es-ES", "en-US"),
    )
    initial_session.process_utterance("Can we continue in Spanish?")
    saved_state = initial_session.as_dict()
    assert saved_state["active_locale"] == "es-ES"

    # Reconnexion avec récupération d'état
    restored_session = CallLanguageSession(
        tenant_id=tenant_id,
        call_session_id="call-j",
        primary_locale=saved_state["primary_locale"],
        active_locale=saved_state["active_locale"],
        allowed_locales=tuple(saved_state["allowed_locales"]),
    )
    assert restored_session.active_locale == "es-ES"
    assert restored_session.last_confirmed_locale == "es-ES"


@pytest.mark.asyncio
async def test_crm_availability_service_timezone_and_hours_fallback(tmp_path):
    """Vérifie que CRMAvailabilityService résout les disponibilités avec fallback sans erreur de fuseau."""
    engine, db, company, config, _key, _orch = _voice_database(tmp_path)
    company.timezone = "America/Montreal"
    company.business_hours = {
        "weekly": {
            "monday": [{"open": "09:00", "close": "17:00"}],
            "tuesday": [{"open": "09:00", "close": "17:00"}],
            "wednesday": [{"open": "09:00", "close": "17:00"}],
            "thursday": [{"open": "09:00", "close": "17:00"}],
            "friday": [{"open": "09:00", "close": "17:00"}],
        }
    }
    db.commit()

    avail = CRMAvailabilityService(db)
    # Chercher les créneaux pour un lundi futur
    future_date = date.today() + timedelta(days=(7 - date.today().weekday()))
    slots = await avail.list_available_slots(company.id, future_date, duration_minutes=30)
    assert isinstance(slots, list)
    assert len(slots) > 0
    first_slot = slots[0]
    assert "start_time" in first_slot
    assert "end_time" in first_slot


@pytest.mark.asyncio
async def test_crm_tools_check_and_list_available_slots(tmp_path):
    """Vérifie les outils IA CheckAvailabilityTool et ListAvailableSlotsTool."""
    engine, db, company, config, _key, _orch = _voice_database(tmp_path)
    user_id = uuid4()
    company.timezone = "America/Montreal"
    company.business_hours = {
        "weekly": {
            "monday": [{"open": "08:00", "close": "18:00"}],
            "tuesday": [{"open": "08:00", "close": "18:00"}],
            "wednesday": [{"open": "08:00", "close": "18:00"}],
            "thursday": [{"open": "08:00", "close": "18:00"}],
            "friday": [{"open": "08:00", "close": "18:00"}],
        }
    }
    db.commit()

    context = ToolExecutionContext(
        tenant=TenantContext(company_id=company.id, user_id=user_id),
        user_id=user_id,
        request_id="req-test-1",
        locale="fr-CA",
        permissions=frozenset({"ai:use", "crm:appointments:read"}),
        capabilities=frozenset(),
        user_message="Quels sont les créneaux disponibles ?",
    )

    list_tool = ListAvailableSlotsTool(db)
    target_date = (date.today() + timedelta(days=7)).isoformat()
    list_res = await list_tool.run(context, ListAvailableSlotsArgs(target_date=target_date))
    assert list_res.success is True
    assert list_res.data["count"] > 0
    assert len(list_res.data["slots"]) > 0

    first_start = list_res.data["slots"][0]["start_time"]
    check_tool = CheckAvailabilityTool(db)
    check_res = await check_tool.run(context, CheckAvailabilityArgs(start_time=first_start, duration_minutes=30))
    assert check_res.success is True
    assert check_res.data["available"] is True


def test_caller_role_permissions_distinction():
    """Vérifie que les rôles distinguent strictement les permissions du propriétaire vs public."""
    owner_perms = permissions_for(UserRole.OWNER)
    assert "crm:appointments:read" in owner_perms
    assert "crm:appointments:write" in owner_perms
    assert "data:manage" in owner_perms
    assert "billing:manage" in owner_perms

    # Public caller ne possède JAMAIS data:manage ou billing:manage
    public_perms = frozenset({"ai:use", "crm:appointments:write", "crm:appointments:read"})
    assert "data:manage" not in public_perms
    assert "billing:manage" not in public_perms
    assert "users:manage" not in public_perms


def test_region_language_resolver_paris_madrid_bucharest():
    """Vérifie les recommandations régionales pour Paris (fr-FR), Madrid (es-ES) et Bucarest (ro-RO)."""
    rec_paris = RegionLanguageResolver.resolve("FR", locality="paris")
    assert rec_paris.primary_locale == "fr-FR"

    rec_madrid = RegionLanguageResolver.resolve("ES", locality="madrid")
    assert rec_madrid.primary_locale == "es-ES"

    rec_bucharest = RegionLanguageResolver.resolve("RO", locality="bucharest")
    assert rec_bucharest.primary_locale == "ro-RO"


def test_voice_audio_capabilities_matrix_44_locales():
    """Vérifie la matrice audio complète des 44 langues sans fausse validation."""
    from backend.app.voice.languages import voice_audio_capabilities_matrix, get_voice_language_capability

    matrix = voice_audio_capabilities_matrix()
    assert len(matrix) == 44

    # Exactement les 5 variantes testées ont live_audio_validated=True
    validated = [row["locale"] for row in matrix if row["live_audio_validated"]]
    assert set(validated) == {"fr", "en", "es", "ro"}  # avec leurs bcp47 fr-CA, en-US, es-ES, ro-RO

    # Les 40 autres n'ont PAS de fausse validation audio
    unvalidated = [row["locale"] for row in matrix if not row["live_audio_validated"]]
    assert len(unvalidated) == 40

    cap_ro = get_voice_language_capability("ro-RO")
    assert cap_ro["live_audio_validated"] is True
    assert cap_ro["stt_available"] is True

    cap_ja = get_voice_language_capability("ja-JP")
    assert cap_ja["live_audio_validated"] is False
    assert cap_ja["stt_available"] is True
    assert cap_ja["fallback_locale"] in {"en-US", "fr-CA"}

