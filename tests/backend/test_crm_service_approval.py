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
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


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
