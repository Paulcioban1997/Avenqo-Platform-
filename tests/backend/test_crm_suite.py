"""Avenqo CRM AI Production Test Suite.

Couvre:
- Isolation multi-tenant stricte (Company A vs Company B)
- Recherche globale multi-entités et tolérance aux accents
- CRUD Clients et Fiche 360
- CRUD Rendez-vous et Détection de conflits / chevauchements
- Moteur de disponibilités (Availability Engine)
- Exécution et contrôle d'accès des outils IA Copilot
- Providers de calendrier
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.ai.tools.contracts import ToolExecutionContext
from backend.app.ai.tools.business.crm_tools import (
    SearchClientsTool,
    SearchClientsArgs,
    GetClientTool,
    GetClientArgs,
    CheckAvailabilityTool,
    CheckAvailabilityArgs,
    CreateAppointmentTool,
    CreateAppointmentArgs,
    GetCRMMetricsTool,
    CRMGenericArgs,
)
from backend.app.models.base import Base
from backend.app.models.company import Company
from backend.app.models.crm import (
    CRMClient,
    CRMService,
    CRMEmployee,
    CRMAppointment,
)
from backend.app.services.crm_service import CRMService as CRMAppService
from backend.app.services.crm_search_service import CRMSearchService
from backend.app.services.crm_availability_service import CRMAvailabilityService
from backend.app.services.calendar.google_provider import GoogleCalendarProvider
from backend.app.services.calendar.outlook_provider import OutlookCalendarProvider
from shared.ai_engine.contracts import TenantContext


@pytest.fixture
def db_session(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'crm_suite_test.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        yield session


def _create_company(session, slug: str) -> Company:
    co = Company(
        id=uuid4(),
        name=f"Company {slug}",
        slug=slug,
        email=f"{slug}@example.com",
        country="CA",
        timezone="America/Toronto",
        industry="Automotive",
        subscription_plan="professional",
    )
    session.add(co)
    session.flush()
    return co


def test_strict_multi_tenant_isolation(db_session):
    """Company A crée Client A. Company B NE DOIT JAMAIS trouver Client A."""
    company_a = _create_company(db_session, "tenant-alpha")
    company_b = _create_company(db_session, "tenant-beta")

    crm_svc = CRMAppService(db_session)
    search_svc = CRMSearchService(db_session)

    # 1. Créer Client A pour Company A
    client_a = crm_svc.create_client(
        company_id=company_a.id,
        data={
            "first_name": "Marc",
            "last_name": "Tremblay",
            "email": "marc.tremblay@quebec.ca",
            "phone": "514-555-0199",
            "company_name": "Garage Tremblay",
        },
    )

    # Vérifier que Company A peut le récupérer
    found_a = crm_svc.get_client(company_a.id, client_a.id)
    assert found_a is not None
    assert found_a.first_name == "Marc"

    # 2. Company B ne peut JAMAIS y accéder par ID direct
    found_by_b = crm_svc.get_client(company_b.id, client_a.id)
    assert found_by_b is None

    # 3. Company B ne peut JAMAIS le trouver par Recherche Globale
    search_res_b = search_svc.search(company_b.id, "Tremblay")
    assert len(search_res_b["clients"]) == 0

    # Alors que Company A le trouve
    search_res_a = search_svc.search(company_a.id, "Tremblay")
    assert len(search_res_a["clients"]) == 1
    assert search_res_a["clients"][0]["id"] == str(client_a.id)

    # 4. Company B ne peut JAMAIS y accéder via l'IA Copilot
    ctx_b = ToolExecutionContext(
        tenant=TenantContext(company_id=company_b.id),
        user_id=uuid4(),
        permissions=frozenset(["ai:use"]),
        request_id="req-b-isolation",
    )
    ai_search_tool = SearchClientsTool(db_session)
    ai_search_res = asyncio.run(ai_search_tool.run(ctx_b, SearchClientsArgs(query="Tremblay")))
    assert ai_search_res.data["count"] == 0

    ai_get_tool = GetClientTool(db_session)
    ai_get_res = asyncio.run(ai_get_tool.run(ctx_b, GetClientArgs(client_id=str(client_a.id))))
    assert ai_get_res.success is False


def test_appointment_crud_and_conflict_detection(db_session):
    """Création de RDV, détection de conflit d'horaire et mise à jour de statut."""
    company = _create_company(db_session, "tenant-appointments")
    crm_svc = CRMAppService(db_session)

    client = crm_svc.create_client(
        company_id=company.id,
        data={
            "first_name": "Sophie",
            "last_name": "Gagnon",
            "email": "sophie@example.com",
        },
    )

    employee = crm_svc.create_employee(
        company_id=company.id,
        data={
            "name": "Jean Mécanicien",
            "role_title": "Mécanicien",
        },
    )

    service = crm_svc.create_service(
        company_id=company.id,
        data={
            "name": "Changement de Pneus",
            "duration_minutes": 60,
            "price": 89.99,
        },
    )

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    slot1_start = now + timedelta(days=1, hours=10)
    slot1_end = slot1_start + timedelta(minutes=60)

    # Créer le premier RDV
    app1, err1 = asyncio.run(
        crm_svc.create_appointment(
            company_id=company.id,
            data={
                "client_id": client.id,
                "service_id": service.id,
                "employee_id": employee.id,
                "title": "Changement de pneus d'hiver",
                "start_time": slot1_start,
                "end_time": slot1_end,
                "duration_minutes": 60,
                "price": 89.99,
            },
        )
    )
    assert app1 is not None
    assert err1 is None
    assert app1.status == "confirmed"

    # Tentative d'un 2e RDV chevauchant avec le MÊME employé (10:30 -> 11:30)
    conflict_start = slot1_start + timedelta(minutes=30)
    conflict_end = conflict_start + timedelta(minutes=60)

    conflict_app, conflict_err = asyncio.run(
        crm_svc.create_appointment(
            company_id=company.id,
            data={
                "client_id": client.id,
                "service_id": service.id,
                "employee_id": employee.id,
                "title": "Conflit attendu",
                "start_time": conflict_start,
                "end_time": conflict_end,
                "duration_minutes": 60,
                "price": 89.99,
            },
        )
    )
    assert conflict_app is None
    assert conflict_err is not None
    assert "Conflit" in conflict_err

    # Même créneau avec un employé DIFFÉRENT -> doit réussir
    employee2 = crm_svc.create_employee(
        company_id=company.id,
        data={
            "name": "Alex Technicien",
            "role_title": "Technicien",
        },
    )
    app2, err2 = asyncio.run(
        crm_svc.create_appointment(
            company_id=company.id,
            data={
                "client_id": client.id,
                "service_id": service.id,
                "employee_id": employee2.id,
                "title": "RDV parallèle sans conflit",
                "start_time": slot1_start,
                "end_time": slot1_end,
                "duration_minutes": 60,
                "price": 89.99,
            },
        )
    )
    assert app2 is not None
    assert err2 is None

    # Modification de statut
    updated_app, update_err = asyncio.run(
        crm_svc.update_appointment(
            company.id, app1.id, data={"status": "completed"}
        )
    )
    assert update_err is None
    assert updated_app is not None
    assert updated_app.status == "completed"


def test_create_appointment_accepts_null_industry_data(db_session):
    company = _create_company(db_session, "tenant-null-industry")
    crm_svc = CRMAppService(db_session)

    client = crm_svc.create_client(
        company_id=company.id,
        data={
            "first_name": "Avenqo",
            "last_name": "Test",
            "email": "avenqo@example.com",
        },
    )

    app, err = asyncio.run(
        crm_svc.create_appointment(
            company_id=company.id,
            data={
                "client_id": client.id,
                "title": "Test production CRM",
                "start_time": datetime.now(timezone.utc) + timedelta(days=2, hours=9),
                "duration_minutes": 30,
                "industry_data": None,
            },
        )
    )

    assert err is None
    assert app is not None
    assert app.industry_data == {}


def test_availability_engine_open_slots(db_session):
    """Vérifie le calcul des créneaux libres sans double réservation."""
    company = _create_company(db_session, "tenant-availability")
    crm_svc = CRMAppService(db_session)
    avail_svc = CRMAvailabilityService(db_session)

    emp = crm_svc.create_employee(
        company_id=company.id,
        data={
            "name": "Pierre Consultant",
            "working_hours": {
                "monday": {"start": "09:00", "end": "12:00"},
                "tuesday": {"start": "09:00", "end": "12:00"},
                "wednesday": {"start": "09:00", "end": "12:00"},
                "thursday": {"start": "09:00", "end": "12:00"},
                "friday": {"start": "09:00", "end": "12:00"},
                "saturday": {"start": "09:00", "end": "12:00"},
                "sunday": {"start": "09:00", "end": "12:00"},
            },
        },
    )

    client = crm_svc.create_client(
        company_id=company.id,
        data={
            "first_name": "Paul",
            "last_name": "Martin",
            "email": "paul.martin@example.ca",
        },
    )

    # Réserver 10:00 -> 11:00
    target_date = (datetime.now(timezone.utc) + timedelta(days=2)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    start_app = target_date.replace(hour=10)
    end_app = start_app + timedelta(minutes=60)

    asyncio.run(
        crm_svc.create_appointment(
            company_id=company.id,
            data={
                "client_id": client.id,
                "employee_id": emp.id,
                "title": "Réunion 10h",
                "start_time": start_app,
                "end_time": end_app,
                "duration_minutes": 60,
            },
        )
    )

    # Vérifier les créneaux disponibles pour 60 min
    slots = asyncio.run(
        avail_svc.list_available_slots(
            company_id=company.id,
            target_date=target_date,
            duration_minutes=60,
            employee_id=emp.id,
        )
    )

    # 9h00 -> 10h00 et 11h00 -> 12h00 doivent être disponibles
    # 10h00 -> 11h00 DOIT ÊTRE OCCUPÉ
    available_starts = [
        datetime.fromisoformat(s["start_time"]).hour for s in slots
    ]
    assert 9 in available_starts
    assert 10 not in available_starts
    assert 11 in available_starts


def test_ai_copilot_crm_tools_execution(db_session):
    """Validation de l'exécution sécurisée des outils IA par le Copilot."""
    company = _create_company(db_session, "tenant-copilot")
    crm_svc = CRMAppService(db_session)

    client = crm_svc.create_client(
        company_id=company.id,
        data={
            "first_name": "Helene",
            "last_name": "Bouchard",
            "email": "helene@example.ca",
        },
    )

    ctx = ToolExecutionContext(
        tenant=TenantContext(company_id=company.id),
        user_id=uuid4(),
        permissions=frozenset(["ai:use"]),
        request_id="copilot-test-1",
    )

    # 1. Vérification métriques KPI
    metrics_tool = GetCRMMetricsTool(db_session)
    metrics_res = asyncio.run(metrics_tool.run(ctx, CRMGenericArgs()))
    assert metrics_res.data["active_clients"] == 1

    # 2. Création de rendez-vous par l'IA
    create_tool = CreateAppointmentTool(db_session)
    future_time = datetime.now(timezone.utc) + timedelta(days=3, hours=14)

    create_res = asyncio.run(
        create_tool.run(
            ctx,
            CreateAppointmentArgs(
                client_name_or_id=str(client.id),
                title="Consultation IA",
                start_time=future_time.isoformat(),
                duration_minutes=45,
            ),
        )
    )
    assert create_res.data["title"] == "Consultation IA"


def test_calendar_provider_abstractions():
    """Vérifie l'instanciation des providers de calendrier Google et Outlook."""
    google = GoogleCalendarProvider()
    assert google.provider_name == "google"

    outlook = OutlookCalendarProvider()
    assert outlook.provider_name == "outlook"
