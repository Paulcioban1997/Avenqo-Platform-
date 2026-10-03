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
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.ai.tools.contracts import ToolExecutionContext
from backend.app.ai.tools.business.crm_tools import (
    SearchClientsTool,
    SearchClientsArgs,
    SearchAppointmentsTool,
    SearchAppointmentsArgs,
    GetClientTool,
    GetClientArgs,
    CheckAvailabilityTool,
    CheckAvailabilityArgs,
    CreateAppointmentTool,
    CreateAppointmentArgs,
    GetCRMMetricsTool,
    CRMGenericArgs,
    UpdateAppointmentTool,
    UpdateAppointmentArgs,
    CancelAppointmentTool,
    CancelAppointmentArgs,
)
from backend.app.models.base import Base
from backend.app.models.company import Company
from backend.app.models.crm import (
    CRMCalendarConnection,
    CRMCustomFieldDefinition,
    CRMCommunication,
    CRMClient,
    CRMService,
    CRMEmployee,
    CRMAppointment,
)
from backend.app.services.crm_service import CRMService as CRMAppService
from backend.app.services.crm_service import _tenant_month_bounds
import backend.app.services.crm_service as crm_service_module
from backend.app.services.crm_notification_service import CRMNotificationService
from backend.app.services.crm_recipient_policy import evaluate_crm_recipient, is_test_email, is_test_phone
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


def test_crm_month_bounds_follow_tenant_timezone_at_utc_month_boundary():
    now = datetime(2026, 10, 1, 2, 0, tzinfo=timezone.utc)

    start, end = _tenant_month_bounds(now, "America/Toronto")

    assert start == datetime(2026, 9, 1, 4, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 10, 1, 4, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("target_date,expected", [
    (None, {"past", "today", "overnight", "tomorrow", "dst-evening"}),
    ("today", {"today", "overnight"}),
    ("2026-10-03", {"today", "overnight"}),
    ("2026-10-05", set()),
    ("2026-11-01", {"dst-evening"}),
])
def test_copilot_appointment_search_reads_real_service_rows_and_tenant_local_day(db_session, monkeypatch, target_date, expected):
    import backend.app.ai.tools.business.crm_tools as crm_tools

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            current = datetime(2026, 10, 4, 2, 0, tzinfo=timezone.utc)
            return current.astimezone(tz) if tz else current.replace(tzinfo=None)

    monkeypatch.setattr(crm_tools, "datetime", FrozenDateTime)
    company = _create_company(db_session, "appointment-reader")
    other = _create_company(db_session, "other-appointment-reader")
    service = CRMAppService(db_session)
    client = service.create_client(company.id, {"first_name": "Local", "last_name": "Client"})
    other_client = service.create_client(other.id, {"first_name": "Other", "last_name": "Client"})
    for owner, customer, title, start in [
        (company, client, "past", datetime(2026, 10, 2, 16, tzinfo=timezone.utc)),
        (company, client, "today", datetime(2026, 10, 3, 4, tzinfo=timezone.utc)),
        (company, client, "overnight", datetime(2026, 10, 4, 3, 30, tzinfo=timezone.utc)),
        (company, client, "tomorrow", datetime(2026, 10, 4, 4, tzinfo=timezone.utc)),
        (company, client, "dst-evening", datetime(2026, 11, 2, 4, 30, tzinfo=timezone.utc)),
        (other, other_client, "private-other-tenant", datetime(2026, 10, 3, 12, tzinfo=timezone.utc)),
    ]:
        db_session.add(CRMAppointment(company_id=owner.id, client_id=customer.id, title=title,
            start_time=start, end_time=start + timedelta(hours=1), duration_minutes=60, status="confirmed"))
    db_session.commit()
    before = db_session.query(CRMAppointment).count()
    context = ToolExecutionContext(tenant=TenantContext(company_id=company.id), user_id=uuid4(),
        permissions=frozenset({"ai:use"}), request_id="appointment-read")
    args = SearchAppointmentsArgs(**({"target_date": target_date} if target_date else {}))
    result = asyncio.run(SearchAppointmentsTool(db_session).run(context, args))
    assert result.success is True
    assert {row["title"] for row in result.data["appointments"]} == expected
    assert result.data["count"] == len(expected)
    assert result.source_refs == ("crm_appointments",)
    assert all("client_email" not in row and "client_phone" not in row for row in result.data["appointments"])
    assert db_session.query(CRMAppointment).count() == before


def test_crm_appointments_this_month_uses_tenant_local_month(db_session, monkeypatch):
    company = _create_company(db_session, "tenant-month-boundary")
    crm_service = CRMAppService(db_session)
    client = crm_service.create_client(
        company_id=company.id,
        data={"first_name": "Monthly", "last_name": "Client", "email": "monthly@example.com"},
    )
    db_session.add(
        CRMAppointment(
            company_id=company.id,
            client_id=client.id,
            title="Existing appointment",
            start_time=datetime(2026, 9, 28, 12, 30, tzinfo=timezone.utc),
            end_time=datetime(2026, 9, 28, 13, 0, tzinfo=timezone.utc),
            duration_minutes=30,
            status="confirmed",
        )
    )
    db_session.commit()

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            instant = datetime(2026, 10, 1, 2, 0, tzinfo=timezone.utc)
            return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)

    monkeypatch.setattr(crm_service_module, "datetime", FrozenDateTime)

    assert crm_service.get_kpis(company.id)["appointments_this_month"] == 1


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


def test_customer_deduplication_reuses_normalized_email_or_phone(db_session):
    company = _create_company(db_session, "tenant-customer-dedup")
    crm_svc = CRMAppService(db_session)

    first = crm_svc.create_client(
        company.id,
        {
            "first_name": "John",
            "last_name": "Smith",
            "email": " JOHN.SMITH@example.com ",
            "phone": "+1 (514) 555-0100",
        },
    )
    by_email = crm_svc.create_client(
        company.id,
        {
            "first_name": "John",
            "last_name": "Different",
            "email": "john.smith@example.com",
            "phone": "514-555-0199",
        },
    )
    by_phone = crm_svc.create_client(
        company.id,
        {
            "first_name": "Another",
            "last_name": "Name",
            "email": "another@example.com",
            "phone": "15145550100",
        },
    )

    assert by_email.id == first.id
    assert by_phone.id == first.id
    assert len(crm_svc.list_clients(company.id)) == 1


def test_custom_fields_are_tenant_scoped_and_unique(db_session):
    company_a = _create_company(db_session, "tenant-custom-fields-a")
    company_b = _create_company(db_session, "tenant-custom-fields-b")
    field = CRMCustomFieldDefinition(
        company_id=company_a.id,
        entity_type="appointment",
        field_key="practitioner",
        label="Practitioner",
        field_type="text",
    )
    db_session.add(field)
    db_session.commit()
    assert db_session.query(CRMCustomFieldDefinition).filter_by(company_id=company_a.id).count() == 1
    assert db_session.query(CRMCustomFieldDefinition).filter_by(company_id=company_b.id).count() == 0


def test_appointment_idempotency_returns_one_record_and_is_tenant_scoped(db_session):
    company_a = _create_company(db_session, "tenant-idempotent-a")
    company_b = _create_company(db_session, "tenant-idempotent-b")
    crm_svc = CRMAppService(db_session)
    client_a = crm_svc.create_client(company_a.id, {
        "first_name": "Alex", "last_name": "A", "email": "alex-a@example.com",
    })
    client_b = crm_svc.create_client(company_b.id, {
        "first_name": "Alex", "last_name": "B", "email": "alex-b@example.com",
    })
    start = datetime.now(timezone.utc).replace(second=0, microsecond=0) + timedelta(days=2)
    payload = {
        "client_id": client_a.id,
        "title": "Consultation",
        "start_time": start,
        "duration_minutes": 30,
        "idempotency_key": "booking-operation-1",
    }

    first, first_error = asyncio.run(crm_svc.create_appointment(company_a.id, payload))
    replay, replay_error = asyncio.run(crm_svc.create_appointment(company_a.id, payload))
    other_tenant, other_error = asyncio.run(
        crm_svc.create_appointment(
            company_b.id,
            {**payload, "client_id": client_b.id},
        )
    )

    assert first_error is None and replay_error is None
    assert first is not None and replay is not None
    assert replay.id == first.id
    assert other_error is None and other_tenant is not None
    assert other_tenant.id != first.id
    assert db_session.query(CRMAppointment).filter_by(company_id=company_a.id).count() == 1
    assert db_session.query(CRMAppointment).filter_by(company_id=company_b.id).count() == 1


def test_customer_resolution_is_exact_and_never_uses_test_mailbox(db_session):
    company = _create_company(db_session, "tenant-customer-resolution")
    crm_svc = CRMAppService(db_session)
    alice = crm_svc.create_client(company.id, {
        "first_name": "Alice", "last_name": "Smith", "email": "alice@customer.ca",
    })
    bob = crm_svc.create_client(company.id, {
        "first_name": "Bob", "last_name": "Smith", "email": "bob@customer.ca",
    })
    test_client = crm_svc.create_client(company.id, {
        "first_name": "Avenqo", "last_name": "CRM Test", "email": "crm_test_client@avenqo.ca",
    })

    resolved_alice, error = crm_svc.resolve_client_for_appointment(company.id, "alice@customer.ca")
    resolved_bob, phone_error = crm_svc.resolve_client_for_appointment(company.id, "Bob")
    ambiguous, ambiguous_error = crm_svc.resolve_client_for_appointment(company.id, "Smith")

    assert resolved_alice is alice and error is None
    assert resolved_bob is bob and phone_error is None
    assert ambiguous is None and ambiguous_error is not None
    assert crm_svc.is_valid_customer_email(test_client.email) is False


def test_crm_notifications_block_seed_recipients_before_transport(db_session, monkeypatch):
    company = _create_company(db_session, "tenant-notification-safety")
    service = CRMAppService(db_session)
    test_client = service.create_client(company.id, {
        "first_name": "Avenqo", "last_name": "CRM Test",
        "email": "crm_test_client@avenqo.ca", "phone": "+15145550199",
    })
    appointment = CRMAppointment(
        company_id=company.id,
        client_id=test_client.id,
        title="Safety test",
        start_time=datetime.now(timezone.utc) + timedelta(days=1),
        end_time=datetime.now(timezone.utc) + timedelta(days=1, minutes=30),
        duration_minutes=30,
        industry_data={},
    )
    db_session.add(appointment)
    db_session.commit()

    sent = []

    class RecordingNotifier:
        def send_transactional(self, recipient, subject, body):
            sent.append(recipient)

    monkeypatch.setattr(
        "backend.app.services.crm_notification_service.get_account_notifier",
        lambda: RecordingNotifier(),
    )
    notifications = CRMNotificationService(db_session)
    asyncio.run(notifications._record(
        company.id, appointment, test_client,
        channel="email", event="created", recipient=test_client.email, status="queued",
    ))
    asyncio.run(notifications._record(
        company.id, appointment, test_client,
        channel="sms", event="created", recipient=test_client.phone, status="queued",
    ))
    db_session.commit()

    communications = db_session.query(CRMCommunication).filter_by(client_id=test_client.id).all()
    assert sent == []
    assert {item.status for item in communications} == {"blocked_test_recipient"}


def test_crm_notifications_send_once_only_to_valid_tenant_contact(db_session, monkeypatch):
    company = _create_company(db_session, "tenant-notification-real")
    service = CRMAppService(db_session)
    client = service.create_client(company.id, {
        "first_name": "Marie", "last_name": "Tremblay",
        "email": "marie@customer.ca", "phone": "+15141234567",
    })
    appointment = CRMAppointment(
        company_id=company.id,
        client_id=client.id,
        title="Consultation",
        start_time=datetime.now(timezone.utc) + timedelta(days=1),
        end_time=datetime.now(timezone.utc) + timedelta(days=1, minutes=30),
        duration_minutes=30,
        industry_data={},
    )
    db_session.add(appointment)
    db_session.commit()
    sent = []

    class RecordingNotifier:
        def send_transactional(self, recipient, subject, body):
            sent.append(recipient)

    monkeypatch.setattr(
        "backend.app.services.crm_notification_service.get_account_notifier",
        lambda: RecordingNotifier(),
    )
    notifications = CRMNotificationService(db_session)
    for _ in range(2):
        asyncio.run(notifications._record(
            company.id, appointment, client,
            channel="email", event="created", recipient=client.email, status="queued",
        ))
        db_session.commit()

    assert sent == ["marie@customer.ca"]
    assert db_session.query(CRMCommunication).filter_by(client_id=client.id).count() == 1
    assert evaluate_crm_recipient(client, company.id, "email").allowed is True


@pytest.mark.parametrize("email", [
    "crm_test_client@avenqo.ca",
    "test@example.com",
    "alice@example.org",
    "demo@production-test.ca",
    "seed@avenqo-e2e.ca",
    "fake.user@customer.ca",
])
def test_crm_recipient_policy_blocks_seed_and_reserved_emails(email):
    assert is_test_email(email) is True


@pytest.mark.parametrize("phone", [None, "", "+15145550199", "+12125550100", "1111111111"])
def test_crm_recipient_policy_blocks_missing_and_fictional_phones(phone):
    assert is_test_phone(phone) is True


def test_copilot_destructive_appointment_tools_require_confirmation(db_session):
    company = _create_company(db_session, "tenant-tool-confirmation")
    client = CRMAppService(db_session).create_client(company.id, {
        "first_name": "Marie", "last_name": "Tremblay", "email": "marie@customer.ca",
    })
    appointment, error = asyncio.run(CRMAppService(db_session).create_appointment(company.id, {
        "client_id": client.id,
        "title": "Consultation",
        "start_time": datetime.now(timezone.utc) + timedelta(days=2),
    }))
    assert error is None and appointment is not None
    original_start = appointment.start_time
    appointment_count = db_session.query(CRMAppointment).filter_by(company_id=company.id).count()
    context = ToolExecutionContext(
        tenant=TenantContext(company_id=company.id),
        user_id=uuid4(),
        permissions=frozenset({"ai:use"}),
        request_id="confirmation-required",
    )

    create = asyncio.run(CreateAppointmentTool(db_session).run(
        context,
        CreateAppointmentArgs(
            client_name_or_id=str(client.id),
            start_time=(datetime.now(timezone.utc) + timedelta(days=4)).isoformat(),
            title="Another consultation",
        ),
    ))
    update = asyncio.run(UpdateAppointmentTool(db_session).run(
        context,
        UpdateAppointmentArgs(
            appointment_id=str(appointment.id),
            new_start_time=(original_start + timedelta(days=1)).isoformat(),
        ),
    ))
    cancel = asyncio.run(CancelAppointmentTool(db_session).run(
        context,
        CancelAppointmentArgs(appointment_id=str(appointment.id)),
    ))
    db_session.refresh(appointment)

    assert create.success is False and create.data["confirmation_required"] is True
    assert db_session.query(CRMAppointment).filter_by(company_id=company.id).count() == appointment_count
    assert update.success is False and update.data["confirmation_required"] is True
    assert cancel.success is False and cancel.data["confirmation_required"] is True
    refreshed_start = appointment.start_time.replace(tzinfo=timezone.utc) if appointment.start_time.tzinfo is None else appointment.start_time
    assert refreshed_start == original_start
    assert appointment.status == "confirmed"


def test_google_attendee_matches_resolved_customer_and_missing_email_is_omitted(db_session, monkeypatch):
    company = _create_company(db_session, "tenant-attendee-identity")
    captured: list[str | None] = []

    class FakeCipher:
        def decrypt(self, value):
            return {"access_token": "runtime-only"}

    class FakeProvider:
        async def create_event(self, credentials, event, calendar_id):
            captured.append(event.attendee_email)
            return f"event-{len(captured)}"

    monkeypatch.setattr("backend.app.services.crm_service.GoogleCalendarProvider", lambda: FakeProvider())
    crm_svc = CRMAppService(db_session, FakeCipher())
    alice = crm_svc.create_client(company.id, {
        "first_name": "Alice", "last_name": "Example", "email": "alice@customer.ca",
    })
    no_email = crm_svc.create_client(company.id, {
        "first_name": "No", "last_name": "Email", "email": "",
    })
    db_session.add(CRMCalendarConnection(
        company_id=company.id,
        provider="google",
        account_email="organizer@avenqo.ca",
        encrypted_credentials="encrypted",
        sync_status="connected",
    ))
    db_session.commit()
    start = datetime.now(timezone.utc) + timedelta(days=2)
    first, first_error = asyncio.run(crm_svc.create_appointment(
        company.id, {"client_id": alice.id, "title": "Alice booking", "start_time": start},
    ))
    second, second_error = asyncio.run(crm_svc.create_appointment(
        company.id, {"client_id": no_email.id, "title": "No email booking", "start_time": start + timedelta(hours=2)},
    ))

    assert first_error is None and second_error is None
    assert first is not None and second is not None
    assert captured == ["alice@customer.ca", None]


def test_google_inbound_sync_is_tenant_scoped_idempotent_and_reflects_cancellation(db_session, monkeypatch):
    company = _create_company(db_session, "tenant-google-inbound")
    alice = CRMAppService(db_session).create_client(company.id, {
        "first_name": "Alice", "last_name": "Example", "email": "alice@customer.ca",
    })
    CRMAppService(db_session).create_client(company.id, {
        "first_name": "Bob", "last_name": "Example", "email": "bob@customer.ca",
    })
    db_session.add(CRMCalendarConnection(
        company_id=company.id,
        provider="google",
        account_email="organizer@example.com",
        encrypted_credentials="encrypted",
        sync_status="connected",
    ))
    db_session.commit()

    class FakeCipher:
        def decrypt(self, value):
            return {"access_token": "runtime-only", "refresh_token": "refresh-only"}

        def encrypt(self, value):
            return "encrypted-refreshed"

    events = [{
        "id": "google-event-1",
        "status": "confirmed",
        "summary": "Physiotherapy",
        "description": "Imported from Google",
        "start": {"dateTime": "2026-10-01T08:30:00-04:00"},
        "end": {"dateTime": "2026-10-01T09:00:00-04:00"},
        "attendees": [{"email": "alice@customer.ca"}],
    }, {
        "id": "google-organizer-only",
        "status": "confirmed",
        "summary": "Personal event",
        "start": {"dateTime": "2026-10-02T08:30:00-04:00"},
        "end": {"dateTime": "2026-10-02T09:00:00-04:00"},
        "attendees": [{"email": "organizer@example.com"}],
    }]

    class FakeProvider:
        def __init__(self, *args):
            pass

        async def list_events(self, *args):
            return events

    monkeypatch.setattr("backend.app.services.crm_service.GoogleCalendarProvider", FakeProvider)
    service = CRMAppService(db_session, FakeCipher())

    first = asyncio.run(service.sync_from_google(company.id))
    second = asyncio.run(service.sync_from_google(company.id))
    appointments = list(db_session.query(CRMAppointment).filter_by(company_id=company.id).all())

    assert first["created"] == 1
    assert first["skipped"] == 1
    assert second["created"] == 0
    assert second["updated"] == 1
    assert len(appointments) == 1
    assert appointments[0].client_id == alice.id
    assert appointments[0].external_event_id == "google-event-1"

    events[0]["status"] = "cancelled"
    cancelled = asyncio.run(service.sync_from_google(company.id))
    db_session.refresh(appointments[0])

    assert cancelled["cancelled"] == 1
    assert appointments[0].status == "cancelled"
    assert appointments[0].is_deleted is False


def test_appointment_search_filters_client_and_title(db_session):
    company = _create_company(db_session, "tenant-appointment-search")
    crm_svc = CRMAppService(db_session)
    client = crm_svc.create_client(company.id, {
        "first_name": "Sarah", "last_name": "Martin", "email": "sarah@example.com",
    })
    start = datetime.now(timezone.utc).replace(second=0, microsecond=0) + timedelta(days=2)
    appointment, error = asyncio.run(crm_svc.create_appointment(company.id, {
        "client_id": client.id,
        "title": "Physiothérapie",
        "start_time": start,
        "duration_minutes": 30,
    }))

    assert error is None and appointment is not None
    results = crm_svc.list_appointments(company.id, search="Sarah", limit=10)
    assert len(results) == 1
    assert results[0]["client_name"] == "Sarah Martin"
    assert crm_svc.list_appointments(company.id, search="inconnu", limit=10) == []


def test_cancel_is_idempotent_and_preserves_history(db_session, monkeypatch):
    monkeypatch.setattr(
        "backend.app.services.crm_notification_service.get_settings",
        lambda: SimpleNamespace(email_delivery_configured=False, telnyx_api_key=None),
    )
    company = _create_company(db_session, "tenant-cancel")
    crm_svc = CRMAppService(db_session)
    client = crm_svc.create_client(company.id, {
        "first_name": "Paul", "last_name": "Martin", "email": "paul@customer.ca",
    })
    appointment, error = asyncio.run(crm_svc.create_appointment(company.id, {
        "client_id": client.id,
        "title": "Consultation",
        "start_time": datetime.now(timezone.utc) + timedelta(days=2),
        "duration_minutes": 30,
    }))
    assert error is None and appointment is not None

    first = asyncio.run(crm_svc.cancel_appointment_detailed(company.id, appointment.id))
    second = asyncio.run(crm_svc.cancel_appointment_detailed(company.id, appointment.id))

    assert first.appointment is not None
    assert first.appointment.status == "cancelled"
    assert second.calendar_sync == "already_cancelled"
    assert db_session.query(CRMAppointment).filter_by(id=appointment.id).one().is_deleted is False
    communications = db_session.query(CRMCommunication).filter_by(appointment_id=appointment.id).all()
    assert {communication.channel for communication in communications} == {"email", "sms"}
    assert {communication.status for communication in communications} == {
        "blocked_external_configuration",
        "blocked_invalid_recipient",
    }


def test_permanent_delete_is_tenant_scoped_and_idempotent(db_session):
    company_a = _create_company(db_session, "tenant-delete-a")
    company_b = _create_company(db_session, "tenant-delete-b")
    crm_svc = CRMAppService(db_session)
    client_a = crm_svc.create_client(company_a.id, {
        "first_name": "Delete", "last_name": "Me", "email": "delete@example.com",
    })
    appointment, error = asyncio.run(crm_svc.create_appointment(company_a.id, {
        "client_id": client_a.id,
        "title": "Delete test",
        "start_time": datetime.now(timezone.utc) + timedelta(days=2),
        "duration_minutes": 30,
    }))
    assert error is None and appointment is not None

    forbidden = asyncio.run(crm_svc.delete_appointment(company_b.id, appointment.id))
    deleted = asyncio.run(crm_svc.delete_appointment(company_a.id, appointment.id))
    replay = asyncio.run(crm_svc.delete_appointment(company_a.id, appointment.id))

    assert forbidden.appointment is None
    assert deleted.appointment is not None and deleted.calendar_sync == "deleted"
    assert replay.appointment is None
    stored = db_session.query(CRMAppointment).filter_by(id=appointment.id).one()
    assert stored.is_deleted is True


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
        user_message="/confirm",
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
                    confirmed=True,
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
