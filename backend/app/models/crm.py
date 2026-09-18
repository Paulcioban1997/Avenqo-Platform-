"""Modèles de données canoniques pour le module CRM AI (Phase 13 & Production CRM Suite)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, TimestampMixin


# --- Prospects & Opportunités (Phase 13 Foundation) ---

class CRMLead(TimestampMixin, Base):
    """Prospect qualifié ou entrant géré par le module CRM AI."""

    __tablename__ = "crm_leads"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(150), nullable=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="website")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="new", index=True)
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=50)  # 0 à 100
    estimated_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    conversion_probability: Mapped[float] = mapped_column(Float, nullable=False, default=0.2)
    next_step: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class CRMOpportunity(TimestampMixin, Base):
    """Opportunité commerciale du pipeline CRM AI."""

    __tablename__ = "crm_opportunities"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    pipeline_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("crm_pipelines.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    stage_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("crm_pipeline_stages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    client_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("crm_clients.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    lead_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("crm_leads.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="CAD")
    stage: Mapped[str] = mapped_column(String(50), nullable=False, default="discovery", index=True)
    probability: Mapped[float] = mapped_column(Float, nullable=False, default=0.2)
    expected_close_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class CRMActivity(TimestampMixin, Base):
    """Interaction, tâche ou recommandation d'action CRM."""

    __tablename__ = "crm_activities"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lead_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("crm_leads.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    client_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("crm_clients.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    activity_type: Mapped[str] = mapped_column(String(50), nullable=False, default="task")
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending", index=True)
    priority: Mapped[str] = mapped_column(String(50), nullable=False, default="medium")
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendation_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)


class CRMContact(TimestampMixin, Base):
    """Client / Contact avec métriques d'engagement, CLV et risque de churn."""

    __tablename__ = "crm_contacts"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    customer_lifetime_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    churn_risk: Mapped[str] = mapped_column(String(50), nullable=False, default="low", index=True)
    churn_risk_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.1)
    churn_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# --- Client 360, Services, Employés, Calendriers et Rendez-vous ---

class CRMClient(TimestampMixin, Base):
    """Fiche client multi-tenant complète avec adaptation sectorielle."""

    __tablename__ = "crm_clients"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    industry_type: Mapped[str] = mapped_column(String(50), nullable=False, default="general")
    # Données sectorielles flexibles (ex: garage: véhicule/plaque/VIN; clinique: dossier/médecin; salon: préférences)
    industry_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active", index=True)  # active, lead, inactive, archived
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    total_revenue: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    attendance_rate: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)  # Pourcentage
    appointments_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class CRMAddress(TimestampMixin, Base):
    """Adresses associées aux clients (domicile, siège, lieu d'intervention)."""

    __tablename__ = "crm_addresses"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    client_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("crm_clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    address_type: Mapped[str] = mapped_column(String(50), nullable=False, default="primary")
    street: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state_province: Mapped[str | None] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[str] = mapped_column(String(20), nullable=False)
    country: Mapped[str] = mapped_column(String(100), nullable=False, default="Canada")


class CRMService(TimestampMixin, Base):
    """Prestation ou service réservable (ex: Changement de pneus, Consultation, Coupe)."""

    __tablename__ = "crm_services"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="CAD")
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    color_hex: Mapped[str | None] = mapped_column(String(20), nullable=True, default="#0076FF")
    buffer_before_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    buffer_after_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)


class CRMEmployee(TimestampMixin, Base):
    """Professionnel, technicien ou praticien assurant les rendez-vous."""

    __tablename__ = "crm_employees"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    role_title: Mapped[str | None] = mapped_column(String(100), nullable=True)
    color_hex: Mapped[str | None] = mapped_column(String(20), nullable=True, default="#00D4FF")
    # Horaires hebdomadaires (ex: {"monday": [{"start": "09:00", "end": "17:00"}], ...})
    working_hours: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)


class CRMAppointment(TimestampMixin, Base):
    """Rendez-vous planifié dans le calendrier CRM et synchronisé aux calendriers externes."""

    __tablename__ = "crm_appointments"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    client_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("crm_clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    service_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("crm_services.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    employee_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("crm_employees.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    # confirmed, pending, cancelled, completed, no_show
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="confirmed", index=True)
    price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="CAD")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    industry_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    calendar_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)  # google, outlook
    external_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)


class CRMNote(TimestampMixin, Base):
    """Note horodatée rattachée à un client, prospect ou rendez-vous."""

    __tablename__ = "crm_notes"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    client_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("crm_clients.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    appointment_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("crm_appointments.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    author_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    author_name: Mapped[str] = mapped_column(String(150), nullable=False, default="Système")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


# --- Pipelines & Opportunités de vente avancées ---

class CRMPipeline(TimestampMixin, Base):
    """Pipeline de vente paramétrable pour le tenant."""

    __tablename__ = "crm_pipelines"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class CRMPipelineStage(TimestampMixin, Base):
    """Étape ordonnée au sein d'un pipeline."""

    __tablename__ = "crm_pipeline_stages"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    pipeline_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("crm_pipelines.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    color_hex: Mapped[str] = mapped_column(String(20), nullable=False, default="#0076FF")
    win_probability: Mapped[float] = mapped_column(Float, nullable=False, default=0.2)


# --- Communications & Rappels ---

class CRMCommunication(TimestampMixin, Base):
    """Historique des communications (SMS, Email, Appels) avec les clients."""

    __tablename__ = "crm_communications"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    client_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("crm_clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    appointment_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("crm_appointments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    channel: Mapped[str] = mapped_column(String(50), nullable=False, default="email")  # email, sms, call
    direction: Mapped[str] = mapped_column(String(20), nullable=False, default="outbound")  # outbound, inbound
    subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="sent")  # sent, delivered, failed
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class CRMReminder(TimestampMixin, Base):
    """Rappels automatisés ou manuels avant un rendez-vous."""

    __tablename__ = "crm_reminders"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    appointment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("crm_appointments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    remind_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(50), nullable=False, default="email")
    is_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# --- Moteur d'Automations CRM ---

class CRMAutomation(TimestampMixin, Base):
    """Règles d'automatisation déclenchées par les événements du cycle de vie CRM."""

    __tablename__ = "crm_automations"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(100), nullable=False)  # appointment_created, appointment_approaching, appointment_cancelled, client_inactive, lead_created
    trigger_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    action_type: Mapped[str] = mapped_column(String(100), nullable=False)  # send_email, send_sms, create_reminder, update_pipeline, assign_employee
    action_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    execution_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# --- Synchronisation Calendriers Externes (Google / Outlook) ---

class CRMCalendarConnection(TimestampMixin, Base):
    """Connexion OAuth sécurisée à un calendrier externe (Google Calendar / Outlook)."""

    __tablename__ = "crm_calendar_connections"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="google")  # google, outlook
    account_email: Mapped[str] = mapped_column(String(255), nullable=False)
    calendar_id: Mapped[str] = mapped_column(String(255), nullable=False, default="primary")
    # Tokens chiffrés au repos via ConnectorSecretCipher (Fernet / MultiFernet)
    encrypted_credentials: Mapped[str] = mapped_column(Text, nullable=False)
    sync_status: Mapped[str] = mapped_column(String(50), nullable=False, default="connected")  # connected, syncing, error, disconnected
    sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# --- Journal d'Audit d'Activité CRM ---

class CRMActivityLog(TimestampMixin, Base):
    """Traçabilité de toutes les actions métier effectuées au sein du CRM."""

    __tablename__ = "crm_activity_log"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)  # client, appointment, service, automation
    entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)  # create, update, reschedule, cancel, complete, sync
    actor_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    actor_name: Mapped[str] = mapped_column(String(150), nullable=False, default="Système / IA")
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
