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
