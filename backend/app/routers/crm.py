"""Routes API pour le module CRM AI (Production Multi-Tenant CRM Suite)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import base64
import hashlib
import hmac
import json
import re
import secrets
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.config.settings import get_settings
from backend.app.core.security import hash_token
from backend.app.database import get_db
from backend.app.dependencies.auth import get_current_identity, get_tenant_context
from backend.app.dependencies.commerce import get_connector_secret_cipher
from backend.app.models.crm import (
    CRMActivity,
    CRMCalendarConnection,
    CRMCustomFieldDefinition,
    CRMContact,
    CRMLead,
    CRMOpportunity,
)
from backend.app.models.commerce_connection import CommerceOAuthState
from backend.app.services.calendar.google_provider import GoogleCalendarProvider
from backend.app.services.connector_secret_cipher import ConnectorSecretCipher
from backend.app.services.crm_availability_service import CRMAvailabilityService
from backend.app.services.crm_intelligence_service import CRMIntelligenceService
from backend.app.services.crm_search_service import CRMSearchService
from backend.app.services.crm_service import CRMService
from shared.ai_engine.contracts import TenantContext

router = APIRouter(prefix="/crm", tags=["crm"])
google_oauth_callback_router = APIRouter(prefix="/crm", tags=["crm-oauth"])


def _google_oauth_state(tenant_id: UUID, user_id: UUID, secret: str) -> str:
    payload = {
        "tenant_id": str(tenant_id),
        "user_id": str(user_id),
        "provider": "google_calendar",
        "nonce": secrets.token_urlsafe(24),
        "expires_at": int(datetime.now(timezone.utc).timestamp()) + 600,
    }
    encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    signature = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def _verify_google_oauth_state(state: str, secret: str) -> dict[str, str]:
    try:
        encoded, signature = state.split(".", 1)
        expected = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("invalid signature")
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        if payload.get("provider") != "google_calendar":
            raise ValueError("unexpected provider")
        if not payload.get("tenant_id") or not payload.get("user_id") or not payload.get("nonce"):
            raise ValueError("missing oauth context")
        if int(payload["expires_at"]) < int(datetime.now(timezone.utc).timestamp()):
            raise ValueError("expired state")
        return payload
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="État OAuth Google invalide ou expiré.") from exc


def _google_redirect_uri(settings) -> str:
    return settings.google_calendar_redirect_uri or (
        "https://api.avenqo.ca/api/v1/crm/calendar/google/callback"
    )


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


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
    email: str | None = None
    phone: str | None = None
    preferred_language: str = "fr"
    company_name: str | None = None
    industry_type: str = "general"
    industry_metadata: dict[str, Any] = Field(default_factory=dict)
    status: str = "active"
    tags: list[str] = Field(default_factory=list)


class CRMCustomFieldDefinitionRequest(BaseModel):
    entity_type: str = Field(default="appointment", min_length=1, max_length=50)
    field_key: str = Field(min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1, max_length=200)
    field_type: str = Field(default="text", pattern=r"^(text|textarea|number|currency|date|datetime|boolean|select|multi_select|phone|email)$")
    required: bool = False
    options: list[str] = Field(default_factory=list)
    industry_template: str | None = Field(default=None, max_length=80)


class UpdateClientRequest(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None
    preferred_language: str | None = None
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
    idempotency_key: str | None = Field(default=None, max_length=255)


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
    query: str | None = Query(default=None),
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0, ge=0),
    tenant: TenantContext = Depends(get_tenant_context),
    service: CRMService = Depends(_get_crm_service),
) -> list[dict[str, Any]]:
    search_term = search or query
    clients = service.list_clients(tenant.company_id, status=status, search=search_term, limit=limit, offset=offset)
    return [
        {
            "id": str(c.id),
            "full_name": c.full_name,
            "first_name": c.first_name,
            "last_name": c.last_name,
            "email": c.email,
            "phone": c.phone,
            "preferred_language": c.preferred_language,
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
    return {
        "id": str(client.id),
        "full_name": client.full_name,
        "first_name": client.first_name,
        "last_name": client.last_name,
        "email": client.email,
        "phone": client.phone,
        "preferred_language": client.preferred_language,
        "company_name": client.company_name,
    }


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
    return {
        "id": str(updated.id),
        "full_name": updated.full_name,
        "email": updated.email,
        "phone": updated.phone,
        "preferred_language": updated.preferred_language,
        "status": updated.status,
    }


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

@router.get("/custom-fields")
def list_custom_field_definitions(
    entity_type: str = Query(default="appointment", max_length=50),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    fields = db.scalars(
        select(CRMCustomFieldDefinition).where(
            CRMCustomFieldDefinition.company_id == tenant.company_id,
            CRMCustomFieldDefinition.entity_type == entity_type,
            CRMCustomFieldDefinition.is_active.is_(True),
        ).order_by(CRMCustomFieldDefinition.created_at.asc())
    ).all()
    return [
        {
            "id": str(field.id),
            "entity_type": field.entity_type,
            "field_key": field.field_key,
            "label": field.label,
            "field_type": field.field_type,
            "required": field.required,
            "options": field.options,
            "industry_template": field.industry_template,
        }
        for field in fields
    ]


@router.post("/custom-fields", status_code=status.HTTP_201_CREATED)
def create_custom_field_definition(
    payload: CRMCustomFieldDefinitionRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    existing = db.scalar(select(CRMCustomFieldDefinition).where(
        CRMCustomFieldDefinition.company_id == tenant.company_id,
        CRMCustomFieldDefinition.entity_type == payload.entity_type,
        CRMCustomFieldDefinition.field_key == payload.field_key,
    ))
    if existing:
        raise HTTPException(status_code=409, detail="Ce champ personnalisé existe déjà.")
    field = CRMCustomFieldDefinition(company_id=tenant.company_id, **payload.model_dump())
    db.add(field)
    db.commit()
    return {"id": str(field.id), **payload.model_dump()}

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
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    tenant: TenantContext = Depends(get_tenant_context),
    service: CRMService = Depends(_get_crm_service),
) -> dict[str, Any]:
    data = payload.model_dump()
    if idempotency_key and not data.get("idempotency_key"):
        data["idempotency_key"] = idempotency_key
    apt, error = await service.create_appointment(tenant.company_id, data)
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
    result = await service.cancel_appointment_detailed(tenant.company_id, appointment_id)
    if result.appointment is None:
        raise HTTPException(status_code=404, detail=result.error or "Rendez-vous introuvable.")
    response = {
        "id": str(appointment_id),
        "status": "cancelled",
        "calendar_sync": result.calendar_sync,
    }
    if result.error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={**response, "error": result.error},
        )
    return response


@router.delete("/appointments/{appointment_id}")
async def delete_appointment(
    appointment_id: UUID,
    tenant: TenantContext = Depends(get_tenant_context),
    service: CRMService = Depends(_get_crm_service),
) -> dict[str, Any]:
    result = await service.delete_appointment(tenant.company_id, appointment_id)
    if result.appointment is None:
        raise HTTPException(status_code=404, detail=result.error or "Rendez-vous introuvable.")
    if result.error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"id": str(appointment_id), "calendar_sync": result.calendar_sync, "error": result.error},
        )
    return {"id": str(appointment_id), "status": "deleted", "calendar_sync": result.calendar_sync}


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
        "calendar_id": conn.calendar_id,
        "sync_status": conn.sync_status,
        "last_synced_at": conn.last_synced_at.isoformat() if conn.last_synced_at else None,
    }


@router.get("/calendar/google/auth-url")
def get_google_calendar_auth_url(
    tenant: TenantContext = Depends(get_tenant_context),
    identity=Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    settings = get_settings()
    if not all(
        (
            settings.google_calendar_client_id,
            settings.google_calendar_client_secret,
            settings.google_calendar_redirect_uri,
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth non configuré sur ce serveur.",
        )
    provider = GoogleCalendarProvider(
        client_id=settings.google_calendar_client_id,
        client_secret=settings.google_calendar_client_secret,
        redirect_uri=_google_redirect_uri(settings),
    )
    state = _google_oauth_state(
        tenant.company_id,
        identity.user.id,
        settings.auth_jwt_secret,
    )
    now = datetime.now(timezone.utc)
    previous_states = db.scalars(
        select(CommerceOAuthState).where(
            CommerceOAuthState.company_id == tenant.company_id,
            CommerceOAuthState.actor_user_id == identity.user.id,
            CommerceOAuthState.provider == "google_calendar",
            CommerceOAuthState.consumed_at.is_(None),
        )
    ).all()
    for previous_state in previous_states:
        previous_state.consumed_at = now
    db.add(
        CommerceOAuthState(
            company_id=tenant.company_id,
            actor_user_id=identity.user.id,
            provider="google_calendar",
            external_account_id="google_calendar",
            state_hash=hash_token(state),
            expires_at=now + timedelta(minutes=10),
        )
    )
    db.commit()
    auth_url = provider.get_auth_url(state)
    return {"auth_url": auth_url}


@google_oauth_callback_router.get("/calendar/google/callback")
async def google_calendar_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    settings = get_settings()
    state_data = _verify_google_oauth_state(state, settings.auth_jwt_secret)
    tenant_id = UUID(state_data["tenant_id"])
    user_id = UUID(state_data["user_id"])
    now = datetime.now(timezone.utc)
    oauth_state = db.scalar(
        select(CommerceOAuthState)
        .where(
            CommerceOAuthState.provider == "google_calendar",
            CommerceOAuthState.state_hash == hash_token(state),
            CommerceOAuthState.consumed_at.is_(None),
        )
        .with_for_update()
    )
    if (
        oauth_state is None
        or _as_utc(oauth_state.expires_at) <= now
        or oauth_state.company_id != tenant_id
        or oauth_state.actor_user_id != user_id
    ):
        raise HTTPException(status_code=400, detail="État OAuth Google invalide ou déjà utilisé.")
    oauth_state.consumed_at = now
    db.add(oauth_state)
    db.commit()

    cipher = get_connector_secret_cipher()
    provider = GoogleCalendarProvider(
        client_id=settings.google_calendar_client_id,
        client_secret=settings.google_calendar_client_secret,
        redirect_uri=_google_redirect_uri(settings),
    )
    tokens = await provider.exchange_code(code)
    encrypted_creds = cipher.encrypt(tokens)
    email = tokens.get("account_email") or "compte-google@avenqo.ca"

    conn = db.scalars(
        select(CRMCalendarConnection).where(
            CRMCalendarConnection.company_id == tenant_id,
            CRMCalendarConnection.provider == "google",
        )
    ).first()
    if conn:
        conn.provider = "google"
        conn.user_id = user_id
        conn.account_email = email
        conn.encrypted_credentials = encrypted_creds
        conn.sync_status = "connected"
        conn.last_synced_at = now
        conn.sync_error = None
    else:
        conn = CRMCalendarConnection(
            company_id=tenant_id,
            user_id=user_id,
            provider="google",
            account_email=email,
            calendar_id="primary",
            encrypted_credentials=encrypted_creds,
            sync_status="connected",
            last_synced_at=now,
        )
        db.add(conn)

    db.commit()
    try:
        await CRMService(db, cipher).sync_from_google(tenant_id)
    except Exception:
        pass
    return RedirectResponse(
        url=f"{settings.frontend_url.rstrip('/')}/integrations?integration=google_calendar&status=connected",
        status_code=303,
    )


@router.get("/calendar/google/calendars")
async def list_google_calendars(
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    conn = db.scalars(
        select(CRMCalendarConnection).where(
            CRMCalendarConnection.company_id == tenant.company_id,
            CRMCalendarConnection.provider == "google",
            CRMCalendarConnection.sync_status == "connected",
        )
    ).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Google Calendar non connecté.")
    try:
        credentials = get_connector_secret_cipher().decrypt(conn.encrypted_credentials)
        calendars = await GoogleCalendarProvider(
            client_id=get_settings().google_calendar_client_id,
            client_secret=get_settings().google_calendar_client_secret,
            redirect_uri=get_settings().google_calendar_redirect_uri,
        ).list_calendars(credentials)
        return {"selected_calendar_id": conn.calendar_id, "calendars": calendars}
    except Exception as exc:
        conn.sync_status = "error"
        conn.sync_error = "Impossible de lire les calendriers Google."
        db.commit()
        raise HTTPException(status_code=502, detail="Calendriers Google indisponibles.") from exc


@router.post("/calendar/google/sync")
async def sync_google_calendar(
    tenant: TenantContext = Depends(get_tenant_context),
    service: CRMService = Depends(_get_crm_service),
) -> dict[str, int]:
    try:
        return await service.sync_from_google(tenant.company_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Synchronisation Google Calendar indisponible.") from exc


@router.get("/calendar/google/events")
async def get_google_calendar_events(
    start: datetime | None = None,
    end: datetime | None = None,
    tenant: TenantContext = Depends(get_tenant_context),
    service: CRMService = Depends(_get_crm_service),
) -> dict[str, list[dict[str, Any]]]:
    now = datetime.now(timezone.utc)
    try:
        events = await service.list_google_events(
            tenant.company_id,
            start_time=start or now,
            end_time=end or now + timedelta(days=365),
        )
        return {"events": events}
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Événements Google Calendar indisponibles.") from exc


class GoogleCalendarSelectionRequest(BaseModel):
    calendar_id: str = Field(min_length=1, max_length=255)


@router.put("/calendar/google/selection")
def select_google_calendar(
    payload: GoogleCalendarSelectionRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    conn = db.scalars(
        select(CRMCalendarConnection).where(
            CRMCalendarConnection.company_id == tenant.company_id,
            CRMCalendarConnection.provider == "google",
            CRMCalendarConnection.sync_status == "connected",
        )
    ).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Google Calendar non connecté.")
    conn.calendar_id = payload.calendar_id
    conn.last_synced_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "selected", "calendar_id": conn.calendar_id}


@router.post("/calendar/disconnect")
def disconnect_calendar(
    tenant: TenantContext = Depends(get_tenant_context),
    service: CRMService = Depends(_get_crm_service),
) -> dict[str, Any]:
    service.disconnect_calendar(tenant.company_id)
    return {"status": "disconnected"}


# --- Avenqo CRM AI Copilot Real Tool Endpoint ---

class CRMCopilotChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    locale: str = "fr"


@router.post("/copilot/chat")
async def crm_copilot_chat(
    req: CRMCopilotChatRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    service: CRMService = Depends(_get_crm_service),
) -> dict[str, Any]:
    msg = req.message.strip().lower()

    # 1. Natural Language Appointment Creation (Target workflow §12)
    # Example: "Crée un rendez-vous aujourd'hui à 14h30 de physiothérapie d'une durée de 30 minutes."
    is_create_intent = any(k in msg for k in [
        "crée un rendez-vous", "créer un rendez-vous", "planifie", "planifier",
        "prendre rendez-vous", "nouveau rendez-vous", "rendez-vous",
        "create an appointment", "create appointment", "schedule appointment",
        "book appointment", "new appointment", "appointment"
    ]) and any(h in msg for h in ["h", ":", "heure", "am", "pm", "at "])

    if is_create_intent:
        now = datetime.now(timezone.utc)
        target_date = now.date()
        date_label = "aujourd'hui" if req.locale == "fr" else "today"

        if "demain" in msg or "tomorrow" in msg:
            target_date = target_date + timedelta(days=1)
            date_label = "demain" if req.locale == "fr" else "tomorrow"

        # Extract time: 14h30, 14:30, 14h
        time_match = re.search(r"(\d{1,2})[h:](\d{2})?", msg)
        hour = 14
        minute = 30
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2)) if time_match.group(2) else 0

        # Extract duration
        duration_match = re.search(r"(\d+)\s*(?:min|minutes?)", msg)
        duration = int(duration_match.group(1)) if duration_match else 30

        # Extract service title
        service_title = "Physiotherapy" if req.locale == "en" else "Physiothérapie"
        if "physio" in msg:
            service_title = "Physiotherapy" if req.locale == "en" else "Physiothérapie"
        elif "massage" in msg or "massoth" in msg:
            service_title = "Massage therapy" if req.locale == "en" else "Massothérapie"
        elif "consult" in msg:
            service_title = "Consultation"
        elif "entretien" in msg or "maintenance" in msg:
            service_title = "Maintenance" if req.locale == "en" else "Entretien"
        elif "répar" in msg or "repair" in msg:
            service_title = "Repair" if req.locale == "en" else "Réparation"

        start_dt = datetime(target_date.year, target_date.month, target_date.day, hour, minute, tzinfo=timezone.utc)
        end_dt = start_dt + timedelta(minutes=duration)

        # Availability / Conflict check
        avail_svc = CRMAvailabilityService(db)
        has_conflict, conflict_reason = avail_svc.check_conflict(tenant.company_id, start_dt, end_dt)
        if has_conflict:
            return {
                "reply": (
                    f"Unable to create appointment: slot is already booked at {hour:02d}:{minute:02d} ({conflict_reason})."
                    if req.locale == "en"
                    else f"Impossible de créer le rendez-vous : créneau occupé à {hour:02d}h{minute:02d} ({conflict_reason})."
                ),
                "status": "conflict",
                "action": "conflict_detected",
                "conflict_reason": conflict_reason,
            }

        email_match = re.search(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", msg)
        phone_match = re.search(r"(?:\+?\d[\d\s().-]{7,}\d)", msg)
        id_match = re.search(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
            msg,
        )
        name_match = re.search(
            r"(?:pour|for)\s+(.+?)(?=\s+(?:demain|tomorrow|aujourd'hui|today|à|at|avec|with|\d{1,2}[h:])\b|$)",
            msg,
        )
        if ("mon adresse courriel" in msg or "my real email" in msg) and not email_match:
            client = None
            resolution_error = "J'ai besoin du courriel ou du numéro de téléphone du client pour identifier le bon dossier."
        else:
            requested_identifier = (
                email_match.group(0)
                if email_match
                else phone_match.group(0)
                if phone_match
                else id_match.group(0)
                if id_match
                else name_match.group(1).strip()
                if name_match
                else ""
            )
            if not requested_identifier:
                client = None
                resolution_error = "J'ai besoin du courriel ou du numéro de téléphone du client pour identifier le bon dossier."
            else:
                try:
                    client_id = UUID(requested_identifier)
                    client = service.get_client(tenant.company_id, client_id)
                    resolution_error = None if client else "Client introuvable dans ce tenant."
                except ValueError:
                    client, resolution_error = service.resolve_client_for_appointment(
                        tenant.company_id,
                        requested_identifier,
                        email=email_match.group(0) if email_match else None,
                        phone=phone_match.group(0) if phone_match else None,
                    )
        if not client:
            return {
                "reply": resolution_error
                if req.locale != "en"
                else "I need the customer's email address or phone number to identify the correct record.",
                "status": "customer_required",
                "action": "appointment_not_created",
            }
        if not service.is_valid_customer_email(client.email):
            return {
                "reply": (
                    "I need the customer's real email address before booking."
                    if req.locale == "en"
                    else "J'ai besoin du courriel réel du client avant de réserver."
                ),
                "status": "customer_required",
                "action": "appointment_not_created",
            }

        apt, err = await service.create_appointment(
            tenant.company_id,
            {
                "client_id": client.id,
                "title": service_title,
                "start_time": start_dt,
                "duration_minutes": duration,
                "notes": f"Created via Avenqo Copilot • {service_title}" if req.locale == "en" else f"Créé via Avenqo Copilot • {service_title}",
            },
            actor_name="Avenqo Copilot",
        )
        if err:
            return {
                "reply": f"Booking error: {err}" if req.locale == "en" else f"Erreur lors de la réservation : {err}",
                "status": "error"
            }

        end_hour = end_dt.hour
        end_minute = end_dt.minute
        reply_msg = (
            f"{service_title} appointment created for {date_label} from {hour:02d}:{minute:02d} to {end_hour:02d}:{end_minute:02d}."
            if req.locale == "en"
            else f"Rendez-vous de {service_title.lower()} créé {date_label} de {hour:02d}h{minute:02d} à {end_hour:02d}h{end_minute:02d}."
        )
        return {
            "reply": reply_msg,
            "status": "success",
            "action": "appointment_created",
            "appointment": {
                "id": str(apt.id),
                "title": apt.title,
                "start_time": apt.start_time.isoformat(),
                "end_time": apt.end_time.isoformat(),
                "status": apt.status,
                "calendar_synced": bool(apt.external_event_id),
            },
        }

    is_en = req.locale == "en"

    # 2. Available Slots / Availability Search
    if any(k in msg for k in ["créneau", "créneaux", "disponibilité", "dispo", "slot", "slots", "libre", "available"]):
        avail_svc = CRMAvailabilityService(db)
        target_date = datetime.now(timezone.utc).date()
        if "demain" in msg or "tomorrow" in msg:
            target_date = target_date + timedelta(days=1)
        slots = await avail_svc.list_available_slots(tenant.company_id, target_date)
        count = len(slots)
        if count == 0:
            date_str = target_date.strftime("%Y-%m-%d") if is_en else target_date.strftime("%d/%m/%Y")
            msg_reply = f"No available slots found for {date_str}." if is_en else f"Aucun créneau libre disponible pour le {date_str}."
            return {
                "reply": msg_reply,
                "status": "success",
                "slots": [],
            }
        sample_slots = slots[:4]
        slots_str = ", ".join([s.get("start_time", "").split("T")[-1][:5] for s in sample_slots])
        date_str = target_date.strftime("%Y-%m-%d") if is_en else target_date.strftime("%d/%m/%Y")
        msg_reply = (
            f"I found {count} available slot(s) for {date_str}. Earliest openings: {slots_str}."
            if is_en
            else f"J'ai trouvé {count} créneau(x) libre(s) pour le {date_str}. Premières disponibilités : {slots_str}."
        )
        return {
            "reply": msg_reply,
            "status": "success",
            "slots": slots,
        }

    # 3. View Today's Appointments
    if any(k in msg for k in ["mes rendez-vous", "rendez-vous aujourd'hui", "agenda", "today's appointments", "my appointments"]):
        today_date = datetime.now(timezone.utc).date()
        appts = service.list_appointments(tenant.company_id, target_date=today_date, limit=10)
        if not appts:
            msg_reply = (
                "Your calendar is completely open for today. No appointments scheduled."
                if is_en
                else "Votre calendrier est entièrement libre pour aujourd'hui. Aucun rendez-vous prévu."
            )
            return {
                "reply": msg_reply,
                "status": "success",
                "appointments": [],
            }
        lines = [
            f"• {a.title} ({a.client.full_name if a.client else ('Client' if not is_en else 'Customer')}) "
            f"{'at' if is_en else 'à'} {a.start_time.strftime('%H:%M')}"
            for a in appts
        ]
        header = f"You have {len(appts)} appointment(s) scheduled today:\n" if is_en else f"Vous avez {len(appts)} rendez-vous prévu(s) aujourd'hui :\n"
        return {
            "reply": header + "\n".join(lines),
            "status": "success",
            "appointments": [{"id": str(a.id), "title": a.title} for a in appts],
        }

    # 4. Search Client
    if any(k in msg for k in ["rechercher un client", "cherche client", "trouver client", "search client", "find client"]):
        query_cleaned = re.sub(r"(rechercher|cherche|trouver|un|le|la|les|client|clients|search|find)", "", msg).strip()
        clients = service.list_clients(tenant.company_id, search=query_cleaned or None, limit=5)
        if not clients:
            msg_reply = f"No clients found matching '{query_cleaned}'." if is_en else f"Aucun client trouvé pour '{query_cleaned}'."
            return {"reply": msg_reply, "status": "success", "clients": []}
        lines = [f"• {c.full_name} ({c.email or c.phone or ('Contact' if not is_en else 'No phone/email')})" for c in clients]
        header = f"{len(clients)} client(s) found:\n" if is_en else f"{len(clients)} client(s) trouvé(s) :\n"
        return {
            "reply": header + "\n".join(lines),
            "status": "success",
            "clients": [{"id": str(c.id), "name": c.full_name} for c in clients],
        }

    # 5. Generate Report / KPIs
    if any(k in msg for k in ["rapport", "kpi", "chiffres", "statistiques", "métriques", "report", "overview"]):
        kpis = service.get_kpis(tenant.company_id)
        cur = kpis.get("currency", "CAD")
        rev = kpis.get("total_revenue_generated", 0.0)
        clients_count = kpis.get("active_clients", 0)
        appts_count = kpis.get("appointments_this_month", 0)
        att_rate = kpis.get("attendance_rate_percent", 0.0)
        if is_en:
            msg_reply = (
                f"Live CRM performance overview:\n"
                f"• Active clients: {clients_count}\n"
                f"• Appointments this month: {appts_count}\n"
                f"• Attendance rate: {att_rate:.1f} %\n"
                f"• Revenue generated: {rev:,.2f} {cur}\n"
                f"All metrics are computed live from your tenant registry."
            )
        else:
            msg_reply = (
                f"Synthèse de vos indicateurs CRM en direct :\n"
                f"• Clients actifs : {clients_count}\n"
                f"• Rendez-vous ce mois : {appts_count}\n"
                f"• Taux de présence : {att_rate:.1f} %\n"
                f"• Revenus générés : {rev:,.2f} {cur}\n"
                f"Toutes ces données sont issues du registre normalisé de votre entreprise."
            )
        return {
            "reply": msg_reply,
            "status": "success",
            "kpis": kpis,
        }

    # 6. Send Reminders Intent
    if any(k in msg for k in ["rappels", "envoyer des rappels", "relance", "reminders", "send reminders"]):
        msg_reply = (
            "24-hour automated reminders and confirmations are active and operational. Notifications trigger automatically based on your configured workflows."
            if is_en
            else "Les rappels automatiques 24h et les confirmations sont actifs et prêts. Les notifications sont envoyées dès que les déclencheurs d'automatisation sont atteints."
        )
        return {
            "reply": msg_reply,
            "status": "success",
        }

    # General Contextual Help Response
    msg_reply = (
        "Hello! I am your live Avenqo Copilot connected directly to your CRM. "
        "I can check availability, schedule or reschedule appointments, search clients, or generate real-time activity reports."
        if is_en
        else "Bonjour ! Je suis votre Copilot Avenqo connecté en temps réel à votre CRM. "
        "Je peux vérifier vos disponibilités, planifier ou déplacer des rendez-vous, "
        "rechercher vos clients ou générer vos rapports d'activité."
    )
    return {
        "reply": msg_reply,
        "status": "success",
    }

