"""Routes API pour le module CRM AI (Production Multi-Tenant CRM Suite)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.config.settings import get_settings
from backend.app.database import get_db
from backend.app.dependencies.auth import get_current_identity, get_tenant_context
from backend.app.dependencies.commerce import get_connector_secret_cipher
from backend.app.models.crm import (
    CRMActivity,
    CRMCalendarConnection,
    CRMContact,
    CRMLead,
    CRMOpportunity,
)
from backend.app.services.calendar.google_provider import GoogleCalendarProvider
from backend.app.services.connector_secret_cipher import ConnectorSecretCipher
from backend.app.services.crm_availability_service import CRMAvailabilityService
from backend.app.services.crm_intelligence_service import CRMIntelligenceService
from backend.app.services.crm_search_service import CRMSearchService
from backend.app.services.crm_service import CRMService
from shared.ai_engine.contracts import TenantContext

router = APIRouter(prefix="/crm", tags=["crm"])


def _get_crm_service(db: Session = Depends(get_db)) -> CRMService:
    cipher: ConnectorSecretCipher | None = None
    try:
        cipher = get_connector_secret_cipher()
    except Exception:
        pass
    return CRMService(db, cipher)


# --- Request & Response Schemas ---

class CreateLeadRequest(BaseModel):
    first_name: str
    last_name: str
    email: str
    phone: str | None = None
    company_name: str | None = None
    job_title: str | None = None
    source: str = "website"
    status: str = "new"
    score: int = 50
    estimated_value: float = 0.0
    conversion_probability: float = 0.2
    next_step: str | None = None
    notes: str | None = None


class CreateClientRequest(BaseModel):
    first_name: str
    last_name: str
    email: str
    phone: str | None = None
    company_name: str | None = None
    industry_type: str = "general"
    industry_metadata: dict[str, Any] = Field(default_factory=dict)
    status: str = "active"
    tags: list[str] = Field(default_factory=list)


class UpdateClientRequest(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None
    company_name: str | None = None
    industry_type: str | None = None
    industry_metadata: dict[str, Any] | None = None
    status: str | None = None
    tags: list[str] | None = None


class CreateAppointmentRequest(BaseModel):
    client_id: UUID
    service_id: UUID | None = None
    employee_id: UUID | None = None
    title: str | None = None
    start_time: datetime
    duration_minutes: int = 60
    end_time: datetime | None = None
    price: float = 0.0
    notes: str | None = None
    industry_data: dict[str, Any] = Field(default_factory=dict)


class UpdateAppointmentRequest(BaseModel):
    title: str | None = None
    start_time: datetime | None = None
    duration_minutes: int | None = None
    end_time: datetime | None = None
    employee_id: UUID | None = None
    status: str | None = None
    price: float | None = None
    notes: str | None = None
    industry_data: dict[str, Any] | None = None


class CreateServiceRequest(BaseModel):
    name: str
    description: str | None = None
    duration_minutes: int = 60
    price: float = 0.0
    currency: str = "CAD"
    category: str | None = None
    color_hex: str = "#0076FF"
    buffer_before_minutes: int = 0
    buffer_after_minutes: int = 0


class CreateEmployeeRequest(BaseModel):
    name: str
    email: str | None = None
    phone: str | None = None
    role_title: str | None = None
    color_hex: str = "#00D4FF"
    working_hours: dict[str, Any] = Field(default_factory=dict)


class CreateNoteRequest(BaseModel):
    client_id: UUID | None = None
    appointment_id: UUID | None = None
    content: str
    pinned: bool = False


class CreateOpportunityRequest(BaseModel):
    title: str
    company_name: str
    amount: float
    currency: str = "CAD"
    stage: str = "discovery"
    probability: float = 0.2
    lead_id: UUID | None = None
    expected_close_date: datetime | None = None
    notes: str | None = None


# --- KPI & Summary Endpoints ---

@router.get("/kpis")
@router.get("/summary")
def get_crm_kpis(
    tenant: TenantContext = Depends(get_tenant_context),
    service: CRMService = Depends(_get_crm_service),
) -> dict[str, Any]:
    """Retourne les KPIs réels calculés directement depuis la base du tenant."""
    return service.get_kpis(tenant.company_id)


# --- Global CRM Search ---

@router.get("/search")
def search_crm(
    q: str = Query(default="", description="Recherche globale sur les entités CRM"),
    limit: int = Query(default=5, ge=1, le=20),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Moteur de recherche globale tolérant aux accents et strictement isolé au tenant."""
    search_service = CRMSearchService(db)
    return search_service.search_all(tenant.company_id, q, limit_per_group=limit)


# --- Client Endpoints ---

@router.get("/clients")
def list_clients(
    status: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0, ge=0),
    tenant: TenantContext = Depends(get_tenant_context),
    service: CRMService = Depends(_get_crm_service),
) -> list[dict[str, Any]]:
    clients = service.list_clients(tenant.company_id, status=status, search=search, limit=limit, offset=offset)
    return [
        {
            "id": str(c.id),
            "full_name": c.full_name,
            "first_name": c.first_name,
            "last_name": c.last_name,
            "email": c.email,
            "phone": c.phone,
            "company_name": c.company_name,
            "industry_type": c.industry_type,
            "industry_metadata": c.industry_metadata,
            "status": c.status,
            "tags": c.tags,
            "total_revenue": c.total_revenue,
            "attendance_rate": c.attendance_rate,
            "appointments_count": c.appointments_count,
            "created_at": c.created_at.isoformat(),
        }
        for c in clients
    ]


@router.post("/clients", status_code=status.HTTP_201_CREATED)
def create_client(
    payload: CreateClientRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    service: CRMService = Depends(_get_crm_service),
) -> dict[str, Any]:
    client = service.create_client(tenant.company_id, payload.model_dump())
    return {"id": str(client.id), "full_name": client.full_name, "email": client.email}


@router.get("/clients/{client_id}")
def get_client(
    client_id: UUID,
    tenant: TenantContext = Depends(get_tenant_context),
    service: CRMService = Depends(_get_crm_service),
) -> dict[str, Any]:
    client = service.get_client(tenant.company_id, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client introuvable.")
    return {
        "id": str(client.id),
        "full_name": client.full_name,
        "first_name": client.first_name,
        "last_name": client.last_name,
        "email": client.email,
        "phone": client.phone,
        "company_name": client.company_name,
        "industry_type": client.industry_type,
        "industry_metadata": client.industry_metadata,
        "status": client.status,
        "tags": client.tags,
        "total_revenue": client.total_revenue,
        "attendance_rate": client.attendance_rate,
        "appointments_count": client.appointments_count,
        "created_at": client.created_at.isoformat(),
    }


@router.put("/clients/{client_id}")
def update_client(
    client_id: UUID,
    payload: UpdateClientRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    service: CRMService = Depends(_get_crm_service),
) -> dict[str, Any]:
    updated = service.update_client(tenant.company_id, client_id, payload.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Client introuvable.")
    return {"id": str(updated.id), "full_name": updated.full_name, "status": updated.status}


@router.get("/clients/{client_id}/360")
def get_client_360(
    client_id: UUID,
    tenant: TenantContext = Depends(get_tenant_context),
    service: CRMService = Depends(_get_crm_service),
) -> dict[str, Any]:
    """Profil Client 360 complet : rendez-vous passés, notes, communications, chiffre d'affaires."""
    profile = service.get_client_360(tenant.company_id, client_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Client introuvable.")
    return profile


# --- Appointment & Calendar Endpoints ---

@router.get("/appointments")
def list_appointments(
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    status: str | None = Query(default=None),
    employee_id: UUID | None = Query(default=None),
    client_id: UUID | None = Query(default=None),
    tenant: TenantContext = Depends(get_tenant_context),
    service: CRMService = Depends(_get_crm_service),
) -> list[dict[str, Any]]:
    return service.list_appointments(
        tenant.company_id,
        start_date=start_date,
        end_date=end_date,
        status=status,
        employee_id=employee_id,
        client_id=client_id,
    )


@router.post("/appointments", status_code=status.HTTP_201_CREATED)
async def create_appointment(
    payload: CreateAppointmentRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    service: CRMService = Depends(_get_crm_service),
) -> dict[str, Any]:
    apt, error = await service.create_appointment(tenant.company_id, payload.model_dump())
    if error:
        raise HTTPException(status_code=400, detail=error)
    return {
        "id": str(apt.id),
        "title": apt.title,
        "start_time": apt.start_time.isoformat(),
        "end_time": apt.end_time.isoformat(),
        "status": apt.status,
        "calendar_provider": apt.calendar_provider,
        "external_event_id": apt.external_event_id,
    }


@router.put("/appointments/{appointment_id}")
async def update_appointment(
    appointment_id: UUID,
    payload: UpdateAppointmentRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    service: CRMService = Depends(_get_crm_service),
) -> dict[str, Any]:
    apt, error = await service.update_appointment(
        tenant.company_id, appointment_id, payload.model_dump(exclude_unset=True)
    )
    if error:
        raise HTTPException(status_code=400, detail=error)
    return {
        "id": str(apt.id),
        "title": apt.title,
        "start_time": apt.start_time.isoformat(),
        "end_time": apt.end_time.isoformat(),
        "status": apt.status,
    }


@router.post("/appointments/{appointment_id}/cancel")
async def cancel_appointment(
    appointment_id: UUID,
    tenant: TenantContext = Depends(get_tenant_context),
    service: CRMService = Depends(_get_crm_service),
) -> dict[str, Any]:
    success = await service.cancel_appointment(tenant.company_id, appointment_id)
    if not success:
        raise HTTPException(status_code=404, detail="Rendez-vous introuvable.")
    return {"id": str(appointment_id), "status": "cancelled"}


@router.get("/availability/slots")
async def get_available_slots(
    target_date: date = Query(..., description="Date cible au format YYYY-MM-DD"),
    service_id: UUID | None = Query(default=None),
    employee_id: UUID | None = Query(default=None),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    cipher: ConnectorSecretCipher | None = None
    try:
        cipher = get_connector_secret_cipher()
    except Exception:
        pass
    avail = CRMAvailabilityService(db, cipher)
    slots = await avail.list_available_slots(
        tenant.company_id, target_date, service_id=service_id, employee_id=employee_id
    )
    return {
        "target_date": target_date.isoformat(),
        "count": len(slots),
        "slots": slots,
    }


# --- Services & Employees Endpoints ---

@router.get("/services")
def list_services(
    tenant: TenantContext = Depends(get_tenant_context),
    service: CRMService = Depends(_get_crm_service),
) -> list[dict[str, Any]]:
    services = service.list_services(tenant.company_id)
    return [
        {
            "id": str(s.id),
            "name": s.name,
            "description": s.description,
            "duration_minutes": s.duration_minutes,
            "price": s.price,
            "currency": s.currency,
            "category": s.category,
            "color_hex": s.color_hex,
        }
        for s in services
    ]


@router.post("/services", status_code=status.HTTP_201_CREATED)
def create_service(
    payload: CreateServiceRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    service: CRMService = Depends(_get_crm_service),
) -> dict[str, Any]:
    svc = service.create_service(tenant.company_id, payload.model_dump())
    return {"id": str(svc.id), "name": svc.name, "price": svc.price}


@router.get("/employees")
def list_employees(
    tenant: TenantContext = Depends(get_tenant_context),
    service: CRMService = Depends(_get_crm_service),
) -> list[dict[str, Any]]:
    employees = service.list_employees(tenant.company_id)
    return [
        {
            "id": str(e.id),
            "name": e.name,
            "email": e.email,
            "phone": e.phone,
            "role_title": e.role_title,
            "color_hex": e.color_hex,
            "working_hours": e.working_hours,
        }
        for e in employees
    ]


@router.post("/employees", status_code=status.HTTP_201_CREATED)
def create_employee(
    payload: CreateEmployeeRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    service: CRMService = Depends(_get_crm_service),
) -> dict[str, Any]:
    emp = service.create_employee(tenant.company_id, payload.model_dump())
    return {"id": str(emp.id), "name": emp.name}


# --- Notes Endpoints ---

@router.post("/notes", status_code=status.HTTP_201_CREATED)
def create_note(
    payload: CreateNoteRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    service: CRMService = Depends(_get_crm_service),
) -> dict[str, Any]:
    note = service.create_note(tenant.company_id, payload.model_dump(), author_name="Utilisateur")
    return {"id": str(note.id), "content": note.content}


# --- Pipelines & Opportunities ---

@router.get("/pipelines")
def list_pipelines(
    tenant: TenantContext = Depends(get_tenant_context),
    service: CRMService = Depends(_get_crm_service),
) -> list[dict[str, Any]]:
    return service.list_pipelines(tenant.company_id)


@router.post("/opportunities", status_code=status.HTTP_201_CREATED)
def create_opportunity(
    payload: CreateOpportunityRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    opp = CRMOpportunity(
        company_id=tenant.company_id,
        title=payload.title,
        company_name=payload.company_name,
        amount=payload.amount,
        currency=payload.currency,
        stage=payload.stage,
        probability=payload.probability,
        lead_id=payload.lead_id,
        expected_close_date=payload.expected_close_date,
        notes=payload.notes,
    )
    db.add(opp)
    db.commit()
    return {"id": str(opp.id), "title": opp.title, "stage": opp.stage}


# --- Automations ---

@router.get("/automations")
def list_automations(
    tenant: TenantContext = Depends(get_tenant_context),
    service: CRMService = Depends(_get_crm_service),
) -> list[dict[str, Any]]:
    autos = service.list_automations(tenant.company_id)
    return [
        {
            "id": str(a.id),
            "name": a.name,
            "trigger_type": a.trigger_type,
            "action_type": a.action_type,
            "is_active": a.is_active,
            "execution_count": a.execution_count,
        }
        for a in autos
    ]


@router.post("/automations/{automation_id}/toggle")
def toggle_automation(
    automation_id: UUID,
    tenant: TenantContext = Depends(get_tenant_context),
    service: CRMService = Depends(_get_crm_service),
) -> dict[str, Any]:
    is_active = service.toggle_automation(tenant.company_id, automation_id)
    return {"id": str(automation_id), "is_active": is_active}


# --- Google Calendar OAuth & Synchronization ---

@router.get("/calendar/connection")
def get_calendar_connection(
    tenant: TenantContext = Depends(get_tenant_context),
    service: CRMService = Depends(_get_crm_service),
) -> dict[str, Any]:
    conn = service.get_calendar_connection(tenant.company_id)
    if not conn:
        return {"connected": False, "provider": None, "account_email": None}
    return {
        "connected": conn.sync_status == "connected",
        "provider": conn.provider,
        "account_email": conn.account_email,
        "sync_status": conn.sync_status,
        "last_synced_at": conn.last_synced_at.isoformat() if conn.last_synced_at else None,
    }


@router.get("/calendar/google/auth-url")
def get_google_calendar_auth_url(
    tenant: TenantContext = Depends(get_tenant_context),
) -> dict[str, str]:
    settings = get_settings()
    provider = GoogleCalendarProvider(
        client_id=settings.google_calendar_client_id,
        client_secret=settings.google_calendar_client_secret,
        redirect_uri=settings.google_calendar_redirect_uri or f"{settings.frontend_url.rstrip('/')}/crm/calendar/callback",
    )
    state = f"tenant:{tenant.company_id}"
    auth_url = provider.get_auth_url(state)
    return {"auth_url": auth_url}


@router.get("/calendar/google/callback")
async def google_calendar_callback(
    code: str = Query(...),
    state: str = Query(...),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    settings = get_settings()
    cipher = get_connector_secret_cipher()
    provider = GoogleCalendarProvider(
        client_id=settings.google_calendar_client_id,
        client_secret=settings.google_calendar_client_secret,
        redirect_uri=settings.google_calendar_redirect_uri or f"{settings.frontend_url.rstrip('/')}/crm/calendar/callback",
    )
    tokens = await provider.exchange_code(code)
    encrypted_creds = cipher.encrypt(tokens)
    email = tokens.get("account_email") or "compte-google@avenqo.ca"

    conn = db.scalars(
        select(CRMCalendarConnection).where(CRMCalendarConnection.company_id == tenant.company_id)
    ).first()
    if conn:
        conn.provider = "google"
        conn.account_email = email
        conn.encrypted_credentials = encrypted_creds
        conn.sync_status = "connected"
        conn.last_synced_at = datetime.now(timezone.utc)
    else:
        conn = CRMCalendarConnection(
            company_id=tenant.company_id,
            provider="google",
            account_email=email,
            calendar_id="primary",
            encrypted_credentials=encrypted_creds,
            sync_status="connected",
            last_synced_at=datetime.now(timezone.utc),
        )
        db.add(conn)

    db.commit()
    return {"status": "success", "account_email": email}


@router.post("/calendar/disconnect")
def disconnect_calendar(
    tenant: TenantContext = Depends(get_tenant_context),
    service: CRMService = Depends(_get_crm_service),
) -> dict[str, Any]:
    service.disconnect_calendar(tenant.company_id)
    return {"status": "disconnected"}
