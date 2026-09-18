"""Outils IA métier pour le module CRM AI (Phase 13 & Production CRM Suite).

Permet à AI Central et à l'assistant conversationnel de planifier des rendez-vous,
vérifier les disponibilités, gérer les clients et analyser les performances CRM sans hallucination.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import UUID
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.ai.tools.base import AITool, ToolArguments
from backend.app.ai.tools.contracts import ToolExecutionContext, ToolResult
from backend.app.services.crm_availability_service import CRMAvailabilityService
from backend.app.services.crm_intelligence_service import CRMIntelligenceService
from backend.app.services.crm_search_service import CRMSearchService
from backend.app.services.crm_service import CRMService


# --- Arguments Schemas ---

class CRMGenericArgs(ToolArguments):
    limit: int = Field(default=5, description="Nombre maximal d'enregistrements à retourner.")


class CRMLeadSearchArgs(ToolArguments):
    prospect_name: str | None = Field(
        default=None,
        description="Nom du prospect, contact ou entreprise pour la recommandation.",
    )


class SearchClientsArgs(ToolArguments):
    query: str = Field(description="Nom, prénom, email, téléphone ou entreprise du client à rechercher.")
    limit: int = Field(default=5, description="Nombre maximal de résultats.")


class GetClientArgs(ToolArguments):
    client_id: str = Field(description="Identifiant UUID du client.")


class SearchAppointmentsArgs(ToolArguments):
    query: str | None = Field(default=None, description="Titre du rendez-vous, nom du client ou notes.")
    status: str | None = Field(default=None, description="Filtrer par statut: confirmed, pending, completed, cancelled, no_show.")
    limit: int = Field(default=10, description="Nombre maximal de rendez-vous.")


class CheckAvailabilityArgs(ToolArguments):
    start_time: str = Field(description="Date et heure de début souhaitée au format ISO (ex: 2026-09-20T14:30:00Z).")
    duration_minutes: int = Field(default=60, description="Durée de la prestation en minutes.")
    employee_id: str | None = Field(default=None, description="UUID optionnel du collaborateur/praticien.")


class ListAvailableSlotsArgs(ToolArguments):
    target_date: str = Field(description="Date cible au format YYYY-MM-DD (ex: 2026-09-20).")
    service_id: str | None = Field(default=None, description="UUID optionnel de la prestation.")
    employee_id: str | None = Field(default=None, description="UUID optionnel du collaborateur/praticien.")


class CreateAppointmentArgs(ToolArguments):
    client_name_or_id: str = Field(description="Nom ou UUID du client.")
    start_time: str = Field(description="Date et heure de début au format ISO (ex: 2026-09-20T14:30:00Z).")
    title: str = Field(description="Intitulé ou motif du rendez-vous (ex: Changement de pneus, Consultation).")
    duration_minutes: int = Field(default=60, description="Durée en minutes.")
    service_name: str | None = Field(default=None, description="Nom de la prestation.")
    notes: str | None = Field(default=None, description="Notes ou spécifications (ex: Véhicule, Plaque d'immatriculation).")


class UpdateAppointmentArgs(ToolArguments):
    appointment_id: str = Field(description="UUID du rendez-vous à déplacer ou modifier.")
    new_start_time: str | None = Field(default=None, description="Nouvelle date et heure au format ISO.")
    new_duration_minutes: int | None = Field(default=None, description="Nouvelle durée en minutes.")
    notes: str | None = Field(default=None, description="Notes mises à jour.")


class CancelAppointmentArgs(ToolArguments):
    appointment_id: str = Field(description="UUID du rendez-vous à annuler.")
    reason: str | None = Field(default=None, description="Raison de l'annulation.")


# --- Tools ---

class GetCRMOverviewTool(AITool):
    name = "get_crm_overview"
    description = (
        "Fournit la vue d'ensemble du CRM de l'entreprise : nombre total de prospects, "
        "valeur totale du pipeline, valeur pondérée, taux de conversion et tâches en attente."
    )
    input_schema = CRMGenericArgs
    required_permissions = ("ai:use",)

    def __init__(self, session: Session) -> None:
        self._service = CRMIntelligenceService(session)

    async def run(self, context: ToolExecutionContext, arguments: CRMGenericArgs) -> ToolResult:
        data = self._service.get_crm_summary(context.tenant.company_id)
        return ToolResult(success=True, data=data, source_refs=("crm_summary",))


class GetLeadsToContactTool(AITool):
    name = "get_leads_to_contact"
    description = (
        "Retourne la liste priorisée des prospects à contacter aujourd'hui, avec score IA, "
        "valeur estimée et motif de priorité."
    )
    input_schema = CRMGenericArgs
    required_permissions = ("ai:use",)

    def __init__(self, session: Session) -> None:
        self._service = CRMIntelligenceService(session)

    async def run(self, context: ToolExecutionContext, arguments: CRMGenericArgs) -> ToolResult:
        leads = self._service.get_leads_to_contact_today(
            context.tenant.company_id, limit=arguments.limit
        )
        return ToolResult(success=True, data={"count": len(leads), "leads_to_contact": leads}, source_refs=("crm_leads",))


class GetRankedLeadsTool(AITool):
    name = "get_ranked_leads"
    description = "Classe les prospects par probabilité de conversion et score prédictif."
    input_schema = CRMGenericArgs
    required_permissions = ("ai:use",)

    def __init__(self, session: Session) -> None:
        self._service = CRMIntelligenceService(session)

    async def run(self, context: ToolExecutionContext, arguments: CRMGenericArgs) -> ToolResult:
        ranked = self._service.get_leads_ranked_by_conversion(
            context.tenant.company_id, limit=arguments.limit
        )
        return ToolResult(success=True, data={"count": len(ranked), "ranked_leads": ranked}, source_refs=("crm_leads",))


class GetHighRiskCustomersTool(AITool):
    name = "get_high_risk_customers"
    description = "Identifie les clients existants à risque d'attrition / départ (churn risk)."
    input_schema = CRMGenericArgs
    required_permissions = ("ai:use",)

    def __init__(self, session: Session) -> None:
        self._service = CRMIntelligenceService(session)

    async def run(self, context: ToolExecutionContext, arguments: CRMGenericArgs) -> ToolResult:
        customers = self._service.get_high_risk_customers(
            context.tenant.company_id, limit=arguments.limit
        )
        return ToolResult(success=True, data={"count": len(customers), "high_risk_customers": customers}, source_refs=("crm_contacts",))


class GetTopRevenueDealsTool(AITool):
    name = "get_top_revenue_deals"
    description = "Identifie les opportunités commerciales représentant le plus de revenus potentiels."
    input_schema = CRMGenericArgs
    required_permissions = ("ai:use",)

    def __init__(self, session: Session) -> None:
        self._service = CRMIntelligenceService(session)

    async def run(self, context: ToolExecutionContext, arguments: CRMGenericArgs) -> ToolResult:
        deals = self._service.get_top_potential_revenue(
            context.tenant.company_id, limit=arguments.limit
        )
        return ToolResult(success=True, data={"count": len(deals), "top_deals": deals}, source_refs=("crm_opportunities",))


class GetFollowUpRecommendationTool(AITool):
    name = "get_follow_up_recommendation"
    description = "Génère une recommandation de suivi et une prochaine action recommandée (Next Best Action)."
    input_schema = CRMLeadSearchArgs
    required_permissions = ("ai:use",)

    def __init__(self, session: Session) -> None:
        self._service = CRMIntelligenceService(session)

    async def run(self, context: ToolExecutionContext, arguments: CRMLeadSearchArgs) -> ToolResult:
        query = arguments.prospect_name or ""
        rec = self._service.generate_follow_up_recommendation(context.tenant.company_id, query=query)
        return ToolResult(success=True, data=rec, source_refs=("crm_leads",))


# --- Action Tools pour la Planification et la Gestion CRM ---

class SearchClientsTool(AITool):
    name = "search_clients"
    description = (
        "Recherche des clients dans la base CRM par nom, prénom, email, téléphone, entreprise ou véhicule. "
        "À utiliser pour identifier un client avant une prise de rendez-vous ou pour consulter sa fiche."
    )
    input_schema = SearchClientsArgs
    required_permissions = ("ai:use",)

    def __init__(self, session: Session) -> None:
        self._crm = CRMService(session)

    async def run(self, context: ToolExecutionContext, arguments: SearchClientsArgs) -> ToolResult:
        clients = self._crm.list_clients(context.tenant.company_id, search=arguments.query, limit=arguments.limit)
        data = [
            {
                "id": str(c.id),
                "full_name": c.full_name,
                "email": c.email,
                "phone": c.phone,
                "company_name": c.company_name,
                "status": c.status,
                "industry_metadata": c.industry_metadata,
            }
            for c in clients
        ]
        return ToolResult(success=True, data={"count": len(data), "clients": data}, source_refs=("crm_clients",))


class GetClientTool(AITool):
    name = "get_client"
    description = "Récupère les détails complets d'un client par son identifiant UUID."
    input_schema = GetClientArgs
    required_permissions = ("ai:use",)

    def __init__(self, session: Session) -> None:
        self._crm = CRMService(session)

    async def run(self, context: ToolExecutionContext, arguments: GetClientArgs) -> ToolResult:
        try:
            cid = UUID(arguments.client_id)
        except ValueError:
            return ToolResult(success=False, data={"error": "Identifiant client invalide."})

        client = self._crm.get_client(context.tenant.company_id, cid)
        if not client:
            return ToolResult(success=False, data={"error": "Client introuvable."})

        return ToolResult(
            success=True,
            data={
                "id": str(client.id),
                "full_name": client.full_name,
                "email": client.email,
                "phone": client.phone,
                "company_name": client.company_name,
                "status": client.status,
                "total_revenue": client.total_revenue,
                "attendance_rate": client.attendance_rate,
                "industry_metadata": client.industry_metadata,
            },
            source_refs=("crm_clients",),
        )


class SearchAppointmentsTool(AITool):
    name = "search_appointments"
    description = (
        "Recherche des rendez-vous par client, motif, notes ou statut."
    )
    input_schema = SearchAppointmentsArgs
    required_permissions = ("ai:use",)

    def __init__(self, session: Session) -> None:
        self._crm = CRMService(session)

    async def run(self, context: ToolExecutionContext, arguments: SearchAppointmentsArgs) -> ToolResult:
        appts = self._crm.list_appointments(
            context.tenant.company_id,
            status=arguments.status,
            search=arguments.query,
            limit=arguments.limit,
        )
        data = [
            {
                "id": str(a.id),
                "title": a.title,
                "client_name": a.client.full_name if a.client else "Client inconnu",
                "start_time": a.start_time.isoformat(),
                "end_time": a.end_time.isoformat(),
                "status": a.status,
                "duration_minutes": a.duration_minutes,
                "notes": a.notes,
            }
            for a in appts
        ]
        return ToolResult(success=True, data={"count": len(data), "appointments": data}, source_refs=("crm_appointments",))


class CheckAvailabilityTool(AITool):
    name = "check_availability"
    description = (
        "Vérifie si un créneau horaire précis est disponible (sans conflit) pour un rendez-vous "
        "en tenant compte des rendez-vous existants et des calendriers synchronisés."
    )
    input_schema = CheckAvailabilityArgs
    required_permissions = ("ai:use",)

    def __init__(self, session: Session) -> None:
        self._avail = CRMAvailabilityService(session)

    async def run(self, context: ToolExecutionContext, arguments: CheckAvailabilityArgs) -> ToolResult:
        try:
            start_dt = datetime.fromisoformat(arguments.start_time.replace("Z", "+00:00"))
        except ValueError:
            return ToolResult(success=False, data={"error": "Format d'heure de début invalide."})

        end_dt = start_dt + timedelta(minutes=arguments.duration_minutes)
        emp_id = UUID(arguments.employee_id) if arguments.employee_id else None

        has_conflict, reason = self._avail.check_conflict(
            context.tenant.company_id, start_dt, end_dt, employee_id=emp_id
        )
        return ToolResult(
            success=True,
            data={
                "available": not has_conflict,
                "start_time": start_dt.isoformat(),
                "end_time": end_dt.isoformat(),
                "conflict_reason": reason,
            },
            source_refs=("crm_appointments",),
        )


class ListAvailableSlotsTool(AITool):
    name = "list_available_slots"
    description = (
        "Calcule et retourne la liste des créneaux horaires disponibles sur une journée donnée. "
        "À utiliser pour répondre à 'Trouve-moi un créneau demain après 14h' ou 'Montre-moi mes disponibilités'."
    )
    input_schema = ListAvailableSlotsArgs
    required_permissions = ("ai:use",)

    def __init__(self, session: Session) -> None:
        self._avail = CRMAvailabilityService(session)

    async def run(self, context: ToolExecutionContext, arguments: ListAvailableSlotsArgs) -> ToolResult:
        try:
            target_date = date.fromisoformat(arguments.target_date)
        except ValueError:
            return ToolResult(success=False, data={"error": "Format de date invalide (YYYY-MM-DD attendu)."})

        svc_id = UUID(arguments.service_id) if arguments.service_id else None
        emp_id = UUID(arguments.employee_id) if arguments.employee_id else None

        slots = await self._avail.list_available_slots(
            context.tenant.company_id, target_date, service_id=svc_id, employee_id=emp_id
        )
        return ToolResult(
            success=True,
            data={"target_date": arguments.target_date, "count": len(slots), "slots": slots},
            source_refs=("crm_appointments",),
        )


class CreateAppointmentTool(AITool):
    name = "create_appointment"
    description = (
        "Crée un rendez-vous dans le CRM et le synchronise automatiquement avec Google Calendar. "
        "Vérifie au préalable les conflits d'horaire."
    )
    input_schema = CreateAppointmentArgs
    required_permissions = ("ai:use",)

    def __init__(self, session: Session) -> None:
        self._crm = CRMService(session)

    async def run(self, context: ToolExecutionContext, arguments: CreateAppointmentArgs) -> ToolResult:
        try:
            start_dt = datetime.fromisoformat(arguments.start_time.replace("Z", "+00:00"))
        except ValueError:
            return ToolResult(success=False, data={"error": "Format de date/heure invalide."})

        # Resolve client by UUID or by search
        client = None
        try:
            cid = UUID(arguments.client_name_or_id)
            client = self._crm.get_client(context.tenant.company_id, cid)
        except ValueError:
            matches = self._crm.list_clients(context.tenant.company_id, search=arguments.client_name_or_id, limit=1)
            if matches:
                client = matches[0]
            else:
                # Auto-create new client on the fly if non-existent
                parts = arguments.client_name_or_id.strip().split(maxsplit=1)
                first = parts[0]
                last = parts[1] if len(parts) > 1 else "Client"
                client = self._crm.create_client(
                    context.tenant.company_id,
                    {"first_name": first, "last_name": last, "email": f"{first.lower()}.{last.lower()}@avenqo-guest.ca"},
                    actor_name="IA Copilot",
                )

        if not client:
            return ToolResult(success=False, data={"error": "Impossible de déterminer le client pour ce rendez-vous."})

        apt_data = {
            "client_id": client.id,
            "title": arguments.title,
            "start_time": start_dt,
            "duration_minutes": arguments.duration_minutes,
            "notes": arguments.notes,
        }
        apt, err = await self._crm.create_appointment(
            context.tenant.company_id, apt_data, actor_name="IA Copilot"
        )
        if err:
            return ToolResult(success=False, data={"error": err})

        return ToolResult(
            success=True,
            data={
                "id": str(apt.id),
                "title": apt.title,
                "client_name": client.full_name,
                "start_time": apt.start_time.isoformat(),
                "end_time": apt.end_time.isoformat(),
                "status": apt.status,
                "calendar_synced": bool(apt.external_event_id),
            },
            source_refs=("crm_appointments",),
        )


class UpdateAppointmentTool(AITool):
    name = "update_appointment"
    description = (
        "Déplace ou modifie les paramètres d'un rendez-vous existant. "
        "Synchronise automatiquement le changement avec Google Calendar."
    )
    input_schema = UpdateAppointmentArgs
    required_permissions = ("ai:use",)

    def __init__(self, session: Session) -> None:
        self._crm = CRMService(session)

    async def run(self, context: ToolExecutionContext, arguments: UpdateAppointmentArgs) -> ToolResult:
        try:
            aid = UUID(arguments.appointment_id)
        except ValueError:
            return ToolResult(success=False, data={"error": "Identifiant rendez-vous invalide."})

        patch_data: dict[str, Any] = {}
        if arguments.new_start_time:
            try:
                patch_data["start_time"] = datetime.fromisoformat(arguments.new_start_time.replace("Z", "+00:00"))
            except ValueError:
                return ToolResult(success=False, data={"error": "Format d'heure invalide."})
        if arguments.new_duration_minutes:
            patch_data["duration_minutes"] = arguments.new_duration_minutes
        if arguments.notes:
            patch_data["notes"] = arguments.notes

        apt, err = await self._crm.update_appointment(
            context.tenant.company_id, aid, patch_data, actor_name="IA Copilot"
        )
        if err:
            return ToolResult(success=False, data={"error": err})

        return ToolResult(
            success=True,
            data={
                "id": str(apt.id),
                "title": apt.title,
                "start_time": apt.start_time.isoformat(),
                "end_time": apt.end_time.isoformat(),
                "status": apt.status,
            },
            source_refs=("crm_appointments",),
        )


class CancelAppointmentTool(AITool):
    name = "cancel_appointment"
    description = "Annule un rendez-vous et supprime l'événement du calendrier synchronisé."
    input_schema = CancelAppointmentArgs
    required_permissions = ("ai:use",)

    def __init__(self, session: Session) -> None:
        self._crm = CRMService(session)

    async def run(self, context: ToolExecutionContext, arguments: CancelAppointmentArgs) -> ToolResult:
        try:
            aid = UUID(arguments.appointment_id)
        except ValueError:
            return ToolResult(success=False, data={"error": "Identifiant rendez-vous invalide."})

        success = await self._crm.cancel_appointment(
            context.tenant.company_id, aid, actor_name="IA Copilot"
        )
        if not success:
            return ToolResult(success=False, data={"error": "Rendez-vous introuvable."})

        return ToolResult(
            success=True,
            data={"appointment_id": arguments.appointment_id, "status": "cancelled"},
            source_refs=("crm_appointments",),
        )


class GetClientHistoryTool(AITool):
    name = "get_client_history"
    description = "Consulte l'historique complet d'un client (rendez-vous passés, chiffre d'affaires, notes et communications)."
    input_schema = GetClientArgs
    required_permissions = ("ai:use",)

    def __init__(self, session: Session) -> None:
        self._crm = CRMService(session)

    async def run(self, context: ToolExecutionContext, arguments: GetClientArgs) -> ToolResult:
        try:
            cid = UUID(arguments.client_id)
        except ValueError:
            return ToolResult(success=False, data={"error": "Identifiant client invalide."})

        profile = self._crm.get_client_360(context.tenant.company_id, cid)
        if not profile:
            return ToolResult(success=False, data={"error": "Client introuvable."})

        return ToolResult(success=True, data=profile, source_refs=("crm_clients",))


class GetCRMMetricsTool(AITool):
    name = "get_crm_metrics"
    description = "Fournit les KPIs réels du CRM : clients actifs, rendez-vous du mois, taux de présence et chiffre d'affaires généré."
    input_schema = CRMGenericArgs
    required_permissions = ("ai:use",)

    def __init__(self, session: Session) -> None:
        self._crm = CRMService(session)

    async def run(self, context: ToolExecutionContext, arguments: CRMGenericArgs) -> ToolResult:
        kpis = self._crm.get_kpis(context.tenant.company_id)
        return ToolResult(success=True, data=kpis, source_refs=("crm_kpis",))
