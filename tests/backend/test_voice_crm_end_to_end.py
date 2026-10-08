"""Tests de validation de bout en bout Avenqo Voice AI + CRM AI (Mission Prioritaire P0).

Valide :
1. Scénario D : Non-régression de l'incident réel observé :
   Turn 1 : « Bonjour, pouvez-vous me prendre un rendez-vous aujourd'hui à 14 h ? »
   Turn 2 : « Allô, est-ce que vous avez fini ? » -> Conservation du contexte et des outils CRM (available_tools > 0).
   Turn 3 : « Pourquoi vous ne pouvez pas ? » -> Accès persistant aux outils.
2. Scénario A : Réservation complète (vérification disponibilité -> recueil infos -> confirmation -> création).
3. Scénario B : Créneau occupé -> proposition de créneaux réellement disponibles (suggested_slots).
4. Auto-création d'un nouveau client lors de la réservation avec nom + courriel.
5. Injection de la date et de l'heure courante du fuseau tenant dans les instructions LLM.
6. Isolation multi-tenant stricte.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from typing import Any, cast
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.ai.chat.chat_service import _localized_system_instruction
from backend.app.ai.tools.business.crm_tools import (
    CheckAvailabilityArgs,
    CheckAvailabilityTool,
    CreateAppointmentArgs,
    CreateAppointmentTool,
    ListAvailableSlotsArgs,
    ListAvailableSlotsTool,
)
from backend.app.ai.tools.contracts import ToolExecutionContext
from backend.app.core.permissions import UserRole, permissions_for
from backend.app.models.crm import CRMAppointment, CRMClient, CRMService
from backend.app.models.voice import VoiceBusinessConfig
from backend.app.services.crm_availability_service import CRMAvailabilityService
from backend.app.services.crm_service import CRMService as BackendCRMService
from shared.ai_engine.contracts import TenantContext
from tests.backend.test_voice_agent import _voice_database


def test_system_instruction_injects_current_date_and_time():
    """Vérifie que la date, l'heure et le jour actuels du tenant sont injectés dans le prompt LLM."""
    instruction = _localized_system_instruction(
        "Base system instruction",
        user_language="fr",
        company_country="CA",
        company_currency="CAD",
        company_timezone="America/Montreal",
        is_voice_call=True,
    )
    assert "Company timezone: America/Montreal" in instruction
    assert "Current date and time:" in instruction
    assert "CRITICAL TOOL CALLING RULE" in instruction
    assert "check_availability" in instruction


@pytest.mark.asyncio
async def test_crm_check_availability_returns_suggested_slots_when_busy(tmp_path):
    """Scénario B : Si un créneau est occupé ou hors horaires, retourne des suggestions réelles."""
    _engine, db, company, _config, _key, _orch = _voice_database(tmp_path)
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
    # Chercher un créneau un futur lundi à 14h
    future_date = date.today() + timedelta(days=(7 - date.today().weekday()))
    future_start = datetime(future_date.year, future_date.month, future_date.day, 14, 0, tzinfo=timezone.utc)

    # 1. Vérifier la disponibilité initiale
    res = await avail.check_availability(company.id, future_start, duration_minutes=60)
    assert res["state"] in ("AVAILABLE", "BUSY")

    # 2. Créer un rendez-vous pour occuper 14h à 15h
    crm = BackendCRMService(db)
    client = crm.create_client(company.id, {"first_name": "Alice", "last_name": "Test", "email": "alice@test.ca"})
    apt_data = {
        "client_id": client.id,
        "title": "Consultation occupée",
        "start_time": future_start,
        "duration_minutes": 60,
    }
    apt, err = await crm.create_appointment(company.id, apt_data)
    assert err is None
    assert apt is not None

    # 3. Vérifier à nouveau 14h : doit être BUSY et proposer d'autres créneaux réels
    res2 = await avail.check_availability(company.id, future_start, duration_minutes=60)
    assert res2["available"] is False
    assert res2["state"] == "BUSY"
    assert "suggested_slots" in res2
    assert isinstance(res2["suggested_slots"], list)


@pytest.mark.asyncio
async def test_create_appointment_tool_auto_creates_new_client_and_books(tmp_path):
    """Scénario A : Un nouvel appelant fournissant son nom et son courriel est inscrit et réservé."""
    _engine, db, company, _config, _key, _orch = _voice_database(tmp_path)
    company.timezone = "America/Montreal"
    db.commit()

    context = ToolExecutionContext(
        tenant=TenantContext(company_id=company.id, user_id=uuid4()),
        user_id=uuid4(),
        request_id="req-book-new-client",
        locale="fr-CA",
        permissions=frozenset({"ai:use", "crm:appointments:write"}),
        capabilities=frozenset(),
        user_message="Je confirme mon rendez-vous pour demain 14h",
    )

    future_start = (datetime.now(timezone.utc) + timedelta(days=2)).replace(hour=14, minute=0, second=0, microsecond=0)
    tool = CreateAppointmentTool(db)

    # Appel avec un client non existant dans la base
    args = CreateAppointmentArgs(
        client_name_or_id="Marc Tremblay",
        client_email="marc.tremblay@gmail.com",
        start_time=future_start.isoformat(),
        title="Consultation initiale",
        duration_minutes=30,
        confirmed=True,
    )
    result = await tool.run(context, args)
    assert result.success is True
    assert result.data["client_name"] == "Marc Tremblay"
    assert result.data["status"] == "confirmed"

    # Vérifier persistance du client dans PostgreSQL
    crm = BackendCRMService(db)
    client = db.scalar(select(CRMClient).where(CRMClient.company_id == company.id, CRMClient.email == "marc.tremblay@gmail.com"))
    assert client is not None
    assert client.first_name == "Marc"
    assert client.last_name == "Tremblay"


@pytest.mark.asyncio
async def test_tool_scope_for_voice_call_never_drops_tools_when_agent_none(tmp_path):
    """Scénario D (Cause racine réelle de l'incident) : Sur /voice, l'IA ne perd jamais ses outils."""
    from backend.app.ai.central.service import CentralAIService
    from backend.app.ai.central.routing import CentralAIIntentRouter
    from backend.app.assistants.registry import build_default_assistant_registry
    from backend.app.ai.tools.business.registry_factory import build_business_tool_registry

    _engine, db, company, _config, _key, _orch = _voice_database(tmp_path)

    class _FakeIngestion:
        pass

    class _FakePredictionService:
        pass

    tool_reg = build_business_tool_registry(db, cast(Any, _FakeIngestion()), cast(Any, _FakePredictionService()))
    asst_reg = build_default_assistant_registry(tool_reg)

    # Simuler le service Central AI
    class MockChat:
        pass

    service = CentralAIService(
        registry=asst_reg,
        chat_service=cast(Any, MockChat()),
        context_builder=cast(Any, None),
        usage_service=cast(Any, None),
    )

    # Cas 1 : Énoncé standard sans mot-clé CRM (« Allô, est-ce que vous avez fini ? »)
    # Sur /voice avec le module "crm" actif : les outils CRM DOIVENT être fournis !
    active_modules = frozenset({"crm", "voice"})
    scope = service._tool_scope_for_request(
        agent=None,
        query="Allô, est-ce que vous avez fini ?",
        page_context="/voice",
        active_modules=active_modules,
    )
    assert scope is not None
    allowed_tools, tool_agents = scope
    assert len(allowed_tools) > 0
    assert "check_availability" in allowed_tools
    assert "create_appointment" in allowed_tools
    assert "list_available_slots" in allowed_tools


def test_multi_tenant_isolation_on_appointments(tmp_path):
    """Scénario E : Cloisonnement strict multi-tenant."""
    _engine, db, company_a, _config_a, _key_a, _orch_a = _voice_database(tmp_path)
    company_b = db.scalar(select(VoiceBusinessConfig).where(VoiceBusinessConfig.company_id != company_a.id))

    crm = BackendCRMService(db)
    client_a = crm.create_client(company_a.id, {"first_name": "Client", "last_name": "A", "email": "a@tenant.ca"})
    assert client_a.company_id == company_a.id

    # Tenant B ne peut jamais voir le client de Tenant A
    client_from_b = crm.get_client(uuid4(), client_a.id)
    assert client_from_b is None


def test_voice_universal_discovery_of_all_authorized_business_modules(tmp_path):
    """Vérifie la découverte dynamique de tous les modules métier autorisés sans hardcoding."""
    from backend.app.ai.central.service import CentralAIService
    from backend.app.assistants.registry import build_default_assistant_registry
    from backend.app.ai.tools.business.registry_factory import build_business_tool_registry

    _engine, db, company, _config, _key, _orch = _voice_database(tmp_path)

    class _FakeIngestion:
        pass

    class _FakePredictionService:
        pass

    tool_reg = build_business_tool_registry(db, cast(Any, _FakeIngestion()), cast(Any, _FakePredictionService()))
    asst_reg = build_default_assistant_registry(tool_reg)

    class MockChat:
        pass

    service = CentralAIService(
        registry=asst_reg,
        chat_service=cast(Any, MockChat()),
        context_builder=cast(Any, None),
        usage_service=cast(Any, None),
    )

    # 1. Tenant avec CRM seul : a les outils CRM, mais ni Retail ni Accounting
    scope_crm = service._tool_scope_for_request(
        agent=None,
        query="Allô ?",
        page_context="/voice",
        active_modules=frozenset({"crm", "voice"}),
    )
    assert scope_crm is not None
    tools_crm, agents_crm = scope_crm
    assert "check_availability" in tools_crm
    assert "get_sales_summary" not in tools_crm
    assert "get_unpaid_invoices" not in tools_crm
    assert "get_subscription_options" not in tools_crm

    # 2. Tenant avec CRM + Retail : a les outils CRM et Retail, mais pas Accounting
    scope_crm_retail = service._tool_scope_for_request(
        agent=None,
        query="Allô ?",
        page_context="/voice",
        active_modules=frozenset({"crm", "retail", "voice"}),
    )
    assert scope_crm_retail is not None
    tools_cr, agents_cr = scope_crm_retail
    assert "check_availability" in tools_cr
    assert "get_sales_summary" in tools_cr
    assert agents_cr["check_availability"] == "crm"
    assert agents_cr["get_sales_summary"] == "retail"
    assert "get_unpaid_invoices" not in tools_cr

    # 3. Tenant complet CRM + Retail + Accounting : découverte universelle de tous les modules métier
    scope_all = service._tool_scope_for_request(
        agent=None,
        query="Allô ?",
        page_context="/voice",
        active_modules=frozenset({"crm", "retail", "accounting", "voice"}),
    )
    assert scope_all is not None
    tools_all, agents_all = scope_all
    assert "check_availability" in tools_all
    assert "get_sales_summary" in tools_all
    assert "get_unpaid_invoices" in tools_all
    assert "get_monthly_expenses" in tools_all
    assert "get_cross_agent_business_health" in tools_all
    assert agents_all["get_unpaid_invoices"] == "accounting"
    assert agents_all["get_cross_agent_business_health"] == "cross_agent"
    # Jamais d'outils d'administration plateforme
    assert "get_subscription_options" not in tools_all


def test_voice_topic_switching_mid_call_preserves_cross_module_capabilities(tmp_path):
    """Vérifie qu'un appelant peut enchaîner RDV, ventes et comptabilité sans blocage."""
    from backend.app.ai.central.service import CentralAIService
    from backend.app.assistants.registry import build_default_assistant_registry
    from backend.app.ai.tools.business.registry_factory import build_business_tool_registry

    _engine, db, company, _config, _key, _orch = _voice_database(tmp_path)

    class _FakeIngestion:
        pass

    class _FakePredictionService:
        pass

    tool_reg = build_business_tool_registry(db, cast(Any, _FakeIngestion()), cast(Any, _FakePredictionService()))
    asst_reg = build_default_assistant_registry(tool_reg)

    class MockChat:
        pass

    service = CentralAIService(
        registry=asst_reg,
        chat_service=cast(Any, MockChat()),
        context_builder=cast(Any, None),
        usage_service=cast(Any, None),
    )

    all_modules = frozenset({"crm", "retail", "accounting", "voice"})

    # Tour 1 : Demande de rendez-vous -> scope /voice donne accès à CRM
    scope_1 = service._tool_scope_for_request(asst_reg.get("crm"), "Prends un rendez-vous demain", "/voice", all_modules)
    assert scope_1 is not None
    tools_1, agents_1 = scope_1
    assert "check_availability" in tools_1
    assert agents_1["check_availability"] == "crm"

    # Tour 2 : Changement de sujet -> Combien de commandes aujourd'hui ?
    scope_2 = service._tool_scope_for_request(asst_reg.get("retail"), "Combien de commandes reçues aujourd'hui ?", "/voice", all_modules)
    assert scope_2 is not None
    tools_2, agents_2 = scope_2
    assert "get_sales_summary" in tools_2
    assert agents_2["get_sales_summary"] == "retail"

    # Tour 3 : Changement de sujet -> Factures impayées ?
    scope_3 = service._tool_scope_for_request(asst_reg.get("accounting"), "Quelles sont les factures impayées ?", "/voice", all_modules)
    assert scope_3 is not None
    tools_3, agents_3 = scope_3
    assert "get_unpaid_invoices" in tools_3
    assert agents_3["get_unpaid_invoices"] == "accounting"


@pytest.mark.asyncio
async def test_list_available_slots_flexible_dates_demain_and_iso(tmp_path):
    """P0 Regression : list_available_slots gère 'demain', 'today', dates relatives et datetimes ISO."""
    _engine, db, company, _config, _key, _orch = _voice_database(tmp_path)
    company.timezone = "America/Montreal"
    company.business_hours = {
        "weekly": {
            "monday": [{"open": "09:00", "close": "17:00"}],
            "tuesday": [{"open": "09:00", "close": "17:00"}],
            "wednesday": [{"open": "09:00", "close": "17:00"}],
            "thursday": [{"open": "09:00", "close": "17:00"}],
            "friday": [{"open": "09:00", "close": "17:00"}],
            "saturday": [{"open": "10:00", "close": "16:00"}],
            "sunday": [{"open": "10:00", "close": "16:00"}],
        }
    }
    db.commit()

    context = ToolExecutionContext(
        tenant=TenantContext(company_id=company.id, user_id=uuid4()),
        user_id=uuid4(),
        request_id="req-slots-demain",
        permissions=frozenset({"ai:use"}),
    )
    tool = ListAvailableSlotsTool(db)

    # 1. Tester 'demain'
    res_demain = await tool.run(context, ListAvailableSlotsArgs(target_date="demain"))
    assert res_demain.success is True
    assert res_demain.data["count"] > 0

    # 2. Tester 'today'
    res_today = await tool.run(context, ListAvailableSlotsArgs(target_date="today"))
    assert res_today.success is True

    # 3. Tester string ISO datetime
    res_iso = await tool.run(context, ListAvailableSlotsArgs(target_date="2026-10-15T14:00:00Z"))
    assert res_iso.success is True
    assert res_iso.data["target_date"] == "2026-10-15"


@pytest.mark.asyncio
async def test_create_appointment_with_client_phone_over_voice(tmp_path):
    """P0 Regression : create_appointment par Voice AI crée le client avec son numéro de téléphone."""
    _engine, db, company, _config, _key, _orch = _voice_database(tmp_path)
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

    context = ToolExecutionContext(
        tenant=TenantContext(company_id=company.id, user_id=uuid4()),
        user_id=uuid4(),
        request_id="req-phone-booking",
        permissions=frozenset({"ai:use", "crm:appointments:write"}),
    )
    tool = CreateAppointmentTool(db)

    future_start = (datetime.now(timezone.utc) + timedelta(days=2)).replace(
        hour=14, minute=0, second=0, microsecond=0
    )
    while future_start.weekday() >= 5:
        future_start += timedelta(days=1)

    args = CreateAppointmentArgs(
        client_name_or_id="Lucie Tremblay",
        client_phone="+15145551234",
        start_time=future_start.isoformat(),
        title="Consultation téléphonique",
        duration_minutes=60,
        confirmed=True,
    )
    res = await tool.run(context, args)
    assert res.success is True
    assert res.data["client_name"] == "Lucie Tremblay"

    # Vérifier client dans la DB
    client = db.scalar(select(CRMClient).where(CRMClient.company_id == company.id, CRMClient.first_name == "Lucie"))
    assert client is not None
    assert client.phone == "15145551234"


@pytest.mark.asyncio
async def test_google_calendar_token_revoked_updates_sync_status_to_error(tmp_path, monkeypatch):
    """P0 Regression : En cas de refresh token révoqué, CRMCalendarConnection passe à sync_status='error'."""
    from backend.app.models.crm import CRMCalendarConnection
    from backend.app.services.calendar.base import CalendarProviderError
    import urllib.error

    _engine, db, company, _config, _key, _orch = _voice_database(tmp_path)
    conn = CRMCalendarConnection(
        company_id=company.id,
        provider="google",
        account_email="owner@test.com",
        encrypted_credentials="enc_creds",
        sync_status="connected",
    )
    db.add(conn)
    db.commit()

    class FakeCipher:
        def decrypt(self, val):
            return {"access_token": "expired", "refresh_token": "revoked_token"}
        def encrypt(self, val):
            return "enc_creds"

    class FailingProvider:
        async def check_busy_slots(self, creds, s, e, cal_id):
            err = CalendarProviderError("401 Unauthorized")
            err.__cause__ = urllib.error.HTTPError("https://oauth2.googleapis.com/token", 401, "Unauthorized", {}, None)
            raise err

        async def refresh_access_token(self, r_tok):
            err = CalendarProviderError("400 Bad Request: invalid_grant")
            err.__cause__ = urllib.error.HTTPError("https://oauth2.googleapis.com/token", 400, "invalid_grant", {}, None)
            raise err

    monkeypatch.setattr("backend.app.services.crm_availability_service.GoogleCalendarProvider", lambda *args: FailingProvider())

    avail = CRMAvailabilityService(db, cipher=FakeCipher())
    future_start = (datetime.now(timezone.utc) + timedelta(days=1)).replace(hour=14, minute=0, second=0, microsecond=0)
    res = await avail.check_availability(company.id, future_start)
    assert res["available"] is False
    assert res["state"] == "EXTERNAL_AVAILABILITY_UNAVAILABLE"

    # Vérifier que sync_status a été persisté à 'error'
    db.refresh(conn)
    assert conn.sync_status == "error"
    assert "reconnect" in (conn.error_message or "").lower()
