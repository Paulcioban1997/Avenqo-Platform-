"""Tests pour la validation explicite des prestations, le parcours OWNER et le blocage fail-closed (P10.1)."""

from __future__ import annotations

import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from fastapi import HTTPException

from backend.app.models.base import Base, UserRole
from backend.app.models.company import Company
from backend.app.models.user import User
from backend.app.models.auth_session import AuthSession
from backend.app.models.crm import CRMService as CRMServiceModel, CRMAppointment
from backend.app.models.audit_log import AuditLogEntry
from backend.app.services.crm_service import CRMService
from backend.app.dependencies.auth import CurrentIdentity
from backend.app.routers.crm import create_service, toggle_service_approval, list_services, CreateServiceRequest
from shared.ai_engine.contracts import TenantContext


@pytest.fixture
def db_session():
    import os
    pg_url = os.environ.get("AVENQO_TEST_POSTGRES_URL")
    if pg_url:
        engine = create_engine(pg_url, echo=False)
    else:
        engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        if not pg_url:
            engine.dispose()


def _make_company() -> Company:
    return Company(
        id=uuid4(),
        name="Produits Ero Test",
        slug=f"produits-ero-{uuid4().hex[:6]}",
        email=f"contact-{uuid4().hex[:6]}@produitsero.ca",
        timezone="America/Montreal",
        country="CA",
        currency_code="CAD",
        industry="Retail",
        subscription_plan="professional",
    )


@pytest.mark.asyncio
async def test_unapproved_nonclinic_draft_service_cannot_be_booked(db_session: Session):
    """Vérifie qu'un service avec category != 'clinic' non approuvé est STRICTEMENT bloqué (fail-closed)."""
    company = _make_company()
    db_session.add(company)
    db_session.commit()

    crm = CRMService(db_session)
    # Service atelier standard mais non approuvé (brouillon ou fictif)
    draft_service = CRMServiceModel(
        company_id=company.id,
        name="Affûtage compétition non approuvé",
        duration_minutes=45,
        price=65.0,
        category="workshop",  # category != clinic !
        is_active=True,
        is_approved_by_owner=False,
        is_published=False,
    )
    db_session.add(draft_service)
    db_session.commit()

    start = datetime.now(timezone.utc) + timedelta(days=2)
    appt, err = await crm.create_appointment(
        company.id,
        {
            "start_time": start,
            "service_id": str(draft_service.id),
            "customer_name": "Jean Client",
        },
    )
    assert appt is None
    assert "approuv" in (err or "").lower()


@pytest.mark.asyncio
async def test_unapproved_demo_service_cannot_be_booked(db_session: Session):
    """Vérifie qu'un service démo clinique non approuvé est également bloqué."""
    company = _make_company()
    db_session.add(company)
    db_session.commit()

    crm = CRMService(db_session)
    demo_service = CRMServiceModel(
        company_id=company.id,
        name="Consultation médicale générale",
        duration_minutes=30,
        price=120.0,
        category="clinic",
        is_active=True,
        is_approved_by_owner=False,
        is_published=False,
    )
    db_session.add(demo_service)
    db_session.commit()

    start = datetime.now(timezone.utc) + timedelta(days=2)
    appt, err = await crm.create_appointment(
        company.id,
        {
            "start_time": start,
            "service_id": str(demo_service.id),
            "customer_name": "Jean Client",
        },
    )
    assert appt is None
    assert "approuv" in (err or "").lower()


@pytest.mark.asyncio
async def test_owner_can_toggle_approval_and_enable_booking(db_session: Session):
    company = _make_company()
    company.business_hours = {
        "weekly": {day: [{"open": "08:00", "close": "20:00"}] for day in [
            "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"
        ]}
    }
    db_session.add(company)
    db_session.commit()

    crm = CRMService(db_session)
    service = CRMServiceModel(
        company_id=company.id,
        name="Réglage fixations de ski",
        duration_minutes=30,
        price=40.0,
        category="ski",
        is_active=True,
        is_approved_by_owner=False,
        is_published=False,
    )
    db_session.add(service)
    db_session.commit()

    # 1. Avant approbation, réservation impossible
    start_unapproved = datetime.now(timezone.utc) + timedelta(days=2)
    appt_fail, err_fail = await crm.create_appointment(
        company.id,
        {"start_time": start_unapproved, "service_id": str(service.id), "customer_name": "Client Avant"},
    )
    assert appt_fail is None
    assert "approuv" in (err_fail or "").lower()

    # 2. Le propriétaire approuve et publie la prestation
    updated = crm.toggle_service_approval(company.id, service.id)
    assert updated is not None
    assert updated.is_approved_by_owner is True
    assert updated.is_published is True

    # 3. Après approbation, la réservation est autorisée
    client = crm.create_client(company.id, {"first_name": "Jean", "last_name": "Client", "email": "jean.client@test.ca"})
    next_monday = datetime.now(timezone.utc) + timedelta(days=(7 - datetime.now(timezone.utc).weekday()))
    start = next_monday.replace(hour=10, minute=0, second=0, microsecond=0)
    appt, err = await crm.create_appointment(
        company.id,
        {
            "start_time": start,
            "service_id": str(service.id),
            "client_id": client.id,
            "customer_name": "Jean Client",
        },
        check_conflicts=False,
    )
    assert err is None
    assert appt is not None
    assert appt.service_id == service.id


def test_non_owner_forbidden_from_approving_service(db_session: Session):
    company = _make_company()
    db_session.add(company)
    db_session.commit()

    user_viewer = User(
        id=uuid4(),
        company_id=company.id,
        email="employee@test.com",
        first_name="Employe",
        last_name="Test",
        password_hash="hashed",
        role=UserRole.VIEWER,
    )
    db_session.add(user_viewer)
    db_session.commit()

    now = datetime.now(timezone.utc)
    auth_sess = AuthSession(
        id=uuid4(),
        user_id=user_viewer.id,
        token_hash="dummy",
        created_at=now,
        expires_at=now + timedelta(hours=1),
    )
    identity_viewer = CurrentIdentity(auth_session=auth_sess, user=user_viewer, raw_token="dummy")

    crm = CRMService(db_session)
    svc = CRMServiceModel(
        company_id=company.id,
        name="Prestation Test",
        duration_minutes=30,
        price=50.0,
        category="custom",
        is_active=True,
        is_approved_by_owner=False,
        is_published=False,
    )
    db_session.add(svc)
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        toggle_service_approval(
            service_id=svc.id,
            tenant=TenantContext(company_id=company.id),
            identity=identity_viewer,
            service=crm,
        )
    assert exc_info.value.status_code == 403
    assert "propriétaire" in str(exc_info.value.detail).lower()


def test_owner_can_toggle_approval_via_endpoint_with_audit_log(db_session: Session):
    company = _make_company()
    db_session.add(company)
    db_session.commit()

    user_owner = User(
        id=uuid4(),
        company_id=company.id,
        email="owner@produitsero.ca",
        first_name="Proprietaire",
        last_name="Ero",
        password_hash="hashed",
        role=UserRole.OWNER,
    )
    db_session.add(user_owner)
    db_session.commit()

    now = datetime.now(timezone.utc)
    auth_sess = AuthSession(
        id=uuid4(),
        user_id=user_owner.id,
        token_hash="dummy",
        created_at=now,
        expires_at=now + timedelta(hours=1),
    )
    identity_owner = CurrentIdentity(auth_session=auth_sess, user=user_owner, raw_token="dummy")

    crm = CRMService(db_session)
    svc = CRMServiceModel(
        company_id=company.id,
        name="Service Démo ou Brouillon",
        duration_minutes=60,
        price=100.0,
        category="workshop",
        is_active=True,
        is_approved_by_owner=False,
        is_published=False,
    )
    db_session.add(svc)
    db_session.commit()

    # Route endpoint call
    res = toggle_service_approval(
        service_id=svc.id,
        tenant=TenantContext(company_id=company.id),
        identity=identity_owner,
        service=crm,
    )
    assert res["id"] == str(svc.id)
    assert res["is_approved_by_owner"] is True
    assert res["is_published"] is True

    # Vérification stricte du journal d'audit
    audit_entry = db_session.scalar(
        select(AuditLogEntry).where(
            AuditLogEntry.company_id == company.id,
            AuditLogEntry.action == "crm_service_approval_toggled",
            AuditLogEntry.target_id == str(svc.id),
        )
    )
    assert audit_entry is not None
    assert audit_entry.actor_user_id == user_owner.id
    assert audit_entry.safe_metadata.get("is_approved_by_owner") is True
    assert audit_entry.safe_metadata.get("is_published") is True


@pytest.mark.asyncio
async def test_voice_agent_and_central_ai_cannot_book_unapproved_service(db_session: Session):
    """Vérifie que la tentative de réservation par Voice/AI échoue pour un service non approuvé."""
    company = _make_company()
    db_session.add(company)
    db_session.commit()

    crm = CRMService(db_session)
    unapproved_svc = CRMServiceModel(
        company_id=company.id,
        name="Consultation non autorisée",
        duration_minutes=30,
        price=80.0,
        category="unverified",
        is_active=True,
        is_approved_by_owner=False,
        is_published=False,
    )
    db_session.add(unapproved_svc)
    db_session.commit()

    # Simulation d'un appel par le moteur Voice
    start = datetime.now(timezone.utc) + timedelta(days=3)
    appt, error = await crm.create_appointment(
        company.id,
        {
            "service_id": str(unapproved_svc.id),
            "title": unapproved_svc.name,
            "start_time": start,
            "duration_minutes": unapproved_svc.duration_minutes,
            "price": unapproved_svc.price,
            "customer_name": "Appelant Vocal",
        },
        actor_name="Avenqo Voice",
    )
    assert appt is None
    assert "approuv" in (error or "").lower()


@pytest.mark.asyncio
async def test_historical_confirmed_appointment_does_not_permit_booking_without_owner_approval(db_session: Session):
    """P10.2: Un ancien rendez-vous confirmé ou complété NE constitue PAS une preuve d'approbation commerciale.
    La réservation d'un nouveau créneau sur ce service reste STRICTEMENT bloquée jusqu'à validation explicite de l'OWNER.
    """
    company = _make_company()
    db_session.add(company)
    db_session.commit()

    crm = CRMService(db_session)
    client = crm.create_client(company.id, {"first_name": "Ancien", "last_name": "Client", "email": "ancien@test.ca"})

    # Prestation historique avec ancien rendez-vous confirmé
    service = CRMServiceModel(
        company_id=company.id,
        name="Prestation Historique Réparations",
        duration_minutes=60,
        price=95.0,
        category="workshop",
        is_active=True,
        is_approved_by_owner=False,  # Non approuvé explicitement par OWNER
        is_published=False,          # Non publié
    )
    db_session.add(service)
    db_session.commit()

    # Ancien rendez-vous confirmé présent dans la base de données
    past_time = datetime.now(timezone.utc) - timedelta(days=60)
    historical_appt = CRMAppointment(
        company_id=company.id,
        client_id=client.id,
        service_id=service.id,
        title="Ancien rendez-vous confirmé 2025",
        status="confirmed",
        start_time=past_time,
        end_time=past_time + timedelta(minutes=60),
    )
    db_session.add(historical_appt)
    db_session.commit()

    # Tentative de nouvelle réservation : doit être STRICTEMENT rejetée (fail-closed)
    start = datetime.now(timezone.utc) + timedelta(days=2)
    appt, err = await crm.create_appointment(
        company.id,
        {
            "start_time": start,
            "service_id": str(service.id),
            "client_id": client.id,
            "customer_name": "Nouveau Client 2026",
        },
    )
    assert appt is None, "La réservation doit être bloquée malgré l'existence d'un ancien rendez-vous confirmé"
    assert "approuv" in (err or "").lower()

    # Préservation historique : l'ancien rendez-vous reste intact
    preserved = db_session.get(CRMAppointment, historical_appt.id)
    assert preserved is not None
    assert preserved.status == "confirmed"


@pytest.mark.asyncio
async def test_new_service_creation_defaults_to_unapproved_and_fails_booking(db_session: Session):
    """Vérifie qu'un nouveau service créé par défaut est unapproved/unpublished et ne peut être réservé."""
    company = _make_company()
    db_session.add(company)
    db_session.commit()

    crm = CRMService(db_session)
    new_svc = crm.create_service(company.id, {
        "name": "Nouveau Service Électrique",
        "duration_minutes": 45,
        "price": 75.0,
        "category": "diagnostic",
    })
    assert new_svc.is_approved_by_owner is False
    assert new_svc.is_published is False

    client = crm.create_client(company.id, {"first_name": "Test", "last_name": "Client", "email": "test@test.ca"})
    start = datetime.now(timezone.utc) + timedelta(days=2)
    appt, err = await crm.create_appointment(
        company.id,
        {
            "start_time": start,
            "service_id": str(new_svc.id),
            "client_id": client.id,
            "customer_name": "Test Client",
        },
    )
    assert appt is None
    assert "approuv" in (err or "").lower()


def test_multi_tenant_isolation_on_service_approval(db_session: Session):
    """Vérifie l'étanchéité multi-tenant : l'OWNER du tenant A ne peut PAS approuver un service du tenant B."""
    company_a = _make_company()
    company_b = _make_company()
    db_session.add_all([company_a, company_b])
    db_session.commit()

    user_owner_a = User(
        id=uuid4(),
        company_id=company_a.id,
        email="owner_a@tenant-a.ca",
        first_name="Proprio",
        last_name="A",
        password_hash="hashed",
        role=UserRole.OWNER,
    )
    db_session.add(user_owner_a)
    db_session.commit()

    now = datetime.now(timezone.utc)
    auth_sess_a = AuthSession(
        id=uuid4(),
        user_id=user_owner_a.id,
        token_hash="dummy_a",
        created_at=now,
        expires_at=now + timedelta(hours=1),
    )
    identity_a = CurrentIdentity(auth_session=auth_sess_a, user=user_owner_a, raw_token="dummy_a")

    crm = CRMService(db_session)
    # Service appartenant au Tenant B
    svc_b = CRMServiceModel(
        company_id=company_b.id,
        name="Prestation Privée Tenant B",
        duration_minutes=30,
        price=50.0,
        category="workshop",
        is_active=True,
        is_approved_by_owner=False,
        is_published=False,
    )
    db_session.add(svc_b)
    db_session.commit()

    # Tentative d'approbation par le Tenant A sur le service du Tenant B via le router
    with pytest.raises(HTTPException) as exc_info:
        toggle_service_approval(
            service_id=svc_b.id,
            tenant=TenantContext(company_id=company_a.id),
            identity=identity_a,
            service=crm,
        )
    assert exc_info.value.status_code == 404
    assert "introuvable" in str(exc_info.value.detail).lower()

    # Vérifie que le service B est resté strictement non approuvé
    svc_b_refreshed = db_session.get(CRMServiceModel, svc_b.id)
    assert svc_b_refreshed is not None
    assert svc_b_refreshed.is_approved_by_owner is False
    assert svc_b_refreshed.is_published is False


def test_central_ai_and_voice_catalog_hides_unapproved_services(db_session: Session):
    """Vérifie que CompanyIntelligenceService ne présente jamais de prestations non approuvées/non publiées."""
    from backend.app.services.company_intelligence_service import CompanyIntelligenceService, CompanyOfferingUnavailable
    from backend.app.services.module_entitlement_service import ModuleEntitlementService

    company = _make_company()
    db_session.add(company)
    db_session.commit()

    tenant = TenantContext(company.id)
    entitlements = ModuleEntitlementService(db_session)
    entitlements.activate_module(tenant, "crm", auto_init_voice=False)

    # 1 service approuvé, 1 service non approuvé
    approved_svc = CRMServiceModel(
        company_id=company.id,
        name="Service Officiel Approuvé",
        duration_minutes=30,
        price=50.0,
        category="workshop",
        is_active=True,
        is_approved_by_owner=True,
        is_published=True,
    )
    unapproved_svc = CRMServiceModel(
        company_id=company.id,
        name="Service Non Approuvé Draft",
        duration_minutes=45,
        price=80.0,
        category="workshop",
        is_active=True,
        is_approved_by_owner=False,
        is_published=False,
    )
    db_session.add_all([approved_svc, unapproved_svc])
    db_session.commit()

    ci_service = CompanyIntelligenceService(db_session)
    profile = ci_service.get_profile(company.id)

    # Seul le service approuvé doit figurer dans les offres configurées
    offered_ids = {s["id"] for s in profile.configured_crm_services}
    assert str(approved_svc.id) in offered_ids
    assert str(unapproved_svc.id) not in offered_ids

    # require_service réussit pour le service approuvé
    matched = ci_service.require_service(company.id, service_id=str(approved_svc.id))
    assert matched["name"] == approved_svc.name

    # require_service échoue pour le service non approuvé
    with pytest.raises(CompanyOfferingUnavailable):
        ci_service.require_service(company.id, service_id=str(unapproved_svc.id))

