"""Avenqo AI Employee Performance Coach tools for Central AI orchestration.

Provides authenticated telephone callers with their personal daily shift briefing,
task progress inspection, task completion mutation, and role-adapted coaching advice.
Strictly requires authenticated staff identity (fail-closed if anonymous), active
company subscription, active employee membership, and RBAC write permissions.
"""

from __future__ import annotations

from typing import Any
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.ai.tools.base import AITool, ToolArguments
from backend.app.ai.tools.contracts import ToolExecutionContext, ToolResult
from backend.app.config.settings import get_settings
from backend.app.core.permissions import permissions_for
from backend.app.models.base import UserRole
from backend.app.models.company import Company
from backend.app.models.company_membership import CompanyMembership
from backend.app.models.user import User
from backend.app.models.voice import VoiceBusinessConfig
from backend.app.services.employee_coach_service import EmployeeCoachService


def _verify_coach_access(
    session: Session,
    context: ToolExecutionContext,
    *,
    write: bool = False,
) -> tuple[bool, str | None, User | None]:
    """Strict authorization gate for coach tools: tenant, user, company status, active membership, RBAC."""
    if not context.tenant.user_id:
        return False, "Le coaching employé requiert une authentification téléphonique préalable par NIP.", None

    if not getattr(get_settings(), "voice_ai_coach_enabled", True):
        return False, "Le module Performance Coach est désactivé sur la plateforme.", None

    voice_cfg = session.scalar(
        select(VoiceBusinessConfig).where(VoiceBusinessConfig.company_id == context.tenant.company_id)
    )
    if voice_cfg is not None and not getattr(voice_cfg, "ai_coach_enabled", True):
        return False, "Le coaching employé est désactivé pour cette entreprise.", None

    company = session.get(Company, context.tenant.company_id)
    company_status_str = str(getattr(company, "status", "")).lower()
    if company is None or company_status_str not in {"active", "companystatus.active"}:
        return False, "Entreprise introuvable ou abonnement inactif.", None

    actor = session.get(User, context.tenant.user_id)
    if actor is None or actor.company_id != context.tenant.company_id:
        return False, "Collaborateur non trouvé ou non autorisé pour cette entreprise.", None

    if not getattr(actor, "is_active", True):
        return False, "Le compte de ce collaborateur est inactif ou désactivé.", None

    membership = session.scalar(
        select(CompanyMembership).where(
            CompanyMembership.user_id == actor.id,
            CompanyMembership.company_id == company.id,
            CompanyMembership.is_active.is_(True),
        )
    )
    if membership is None:
        return False, "Adhésion active (CompanyMembership) obligatoire et introuvable pour ce collaborateur.", None

    if write:
        user_role = getattr(membership, "role", None) or getattr(actor, "role", None)
        if user_role == UserRole.VIEWER:
            return False, "Les comptes en lecture seule ne sont pas autorisés à modifier des tâches.", None
        perms = set(context.permissions or ())
        if user_role:
            perms.update(permissions_for(user_role))
        has_task_write = bool(
            {"tasks:own", "tasks:write", "workspace:tasks:write"} & perms
        )
        if not has_task_write:
            return False, "Permission insuffisante pour modifier des tâches.", None

    return True, None, actor


class EmptyCoachArgs(ToolArguments):
    pass


class TaskStatusArgs(ToolArguments):
    status: str | None = Field(default=None, description="Filtre de statut : open, in_progress, done")


class CompleteTaskArgs(ToolArguments):
    task_identifier: str = Field(
        ...,
        description="Identifiant UUID de la tâche ou mot-clé caractéristique de son titre",
    )
    confirmed: bool = Field(
        default=False,
        description="Doit être mis à True UNIQUEMENT après confirmation explicite de l'employé au téléphone",
    )
    confirmation_token: str | None = Field(
        default=None,
        description="Jeton de confirmation émis par le serveur lors de la demande préalable. Preuve obligatoire pour valider la mutation.",
    )
    session_id: str | None = Field(
        default=None,
        description="Identifiant de session d'appel téléphonique rattachée.",
    )
    turn_id: str | None = Field(
        default=None,
        description="Identifiant ou numéro de tour vocal de dialogue.",
    )


class CoachingAdviceArgs(ToolArguments):
    topic: str | None = Field(
        default=None,
        description="Sujet de coaching : ventes, accueil, organisation, motivation, objection client",
    )


class GetMyDailyBriefingTool(AITool):
    name = "get_my_daily_briefing"
    description = (
        "Fournit le briefing quotidien personnalisé du collaborateur authentifié : "
        "les trois priorités du jour, l'ordre d'exécution conseillé, les rendez-vous prévus, "
        "des recommandations concrètes adaptées au métier et un encouragement professionnel motivant."
    )
    input_schema = EmptyCoachArgs
    required_permissions = ("ai:use",)
    read_only = True
    mutates = False
    agent_ids = frozenset({"voice", "coach", "central"})

    def __init__(self, session: Session) -> None:
        self._session = session

    async def run(self, context: ToolExecutionContext, arguments: EmptyCoachArgs) -> ToolResult:
        ok, err, actor = _verify_coach_access(self._session, context, write=False)
        if not ok or actor is None:
            return ToolResult(success=False, error=err or "unauthorized")

        coach = EmployeeCoachService(self._session)
        locale = getattr(context, "locale", "fr-CA") or "fr-CA"
        briefing = coach.get_daily_briefing(actor, locale=str(locale))

        return ToolResult(
            success=True,
            data=briefing,
            metadata={"message": briefing.get("spoken_summary", "Briefing quotidien généré avec succès.")},
        )


class GetMyTasksTool(AITool):
    name = "get_my_tasks"
    description = (
        "Consulte la liste des tâches réellement assignées au collaborateur authentifié "
        "dans l'espace de travail d'entreprise (titre, priorité, échéance, statut)."
    )
    input_schema = TaskStatusArgs
    required_permissions = ("ai:use",)
    read_only = True
    mutates = False
    agent_ids = frozenset({"voice", "coach", "central"})

    def __init__(self, session: Session) -> None:
        self._session = session

    async def run(self, context: ToolExecutionContext, arguments: TaskStatusArgs) -> ToolResult:
        ok, err, actor = _verify_coach_access(self._session, context, write=False)
        if not ok or actor is None:
            return ToolResult(success=False, error=err or "unauthorized")

        coach = EmployeeCoachService(self._session)
        tasks = coach.get_my_tasks(actor, status=arguments.status)
        return ToolResult(
            success=True,
            data={"count": len(tasks), "tasks": tasks},
            metadata={"message": f"{len(tasks)} tâche(s) assignée(s) trouvée(s)."},
        )


class MarkMyTaskCompletedTool(AITool):
    name = "mark_my_task_completed"
    description = (
        "Marque comme terminée une tâche assignée au collaborateur authentifié, "
        "par son identifiant UUID ou un mot-clé précis de son titre, avec confirmation explicite requise."
    )
    input_schema = CompleteTaskArgs
    required_permissions = ("ai:use", "tasks:own")
    read_only = False
    mutates = True
    mutation_capabilities = frozenset({"workspace:tasks:write", "tasks:own"})
    confirmation_policy = "explicit_user_confirmation"
    confirmation_field = "confirmed"
    agent_ids = frozenset({"voice", "coach", "central"})

    def __init__(self, session: Session) -> None:
        self._session = session

    async def run(self, context: ToolExecutionContext, arguments: CompleteTaskArgs) -> ToolResult:
        ok, err, actor = _verify_coach_access(self._session, context, write=True)
        if not ok or actor is None:
            return ToolResult(success=False, error=err or "unauthorized")

        session_id = (
            getattr(context, "session_id", None)
            or getattr(context.tenant, "session_id", None)
            or getattr(arguments, "session_id", None)
            or getattr(context, "request_id", None)
        )
        turn_id = getattr(context, "turn_id", None) or getattr(arguments, "turn_id", None)
        coach = EmployeeCoachService(self._session)
        result = coach.complete_task(
            actor,
            arguments.task_identifier,
            confirmed=arguments.confirmed,
            confirmation_token=arguments.confirmation_token,
            session_id=str(session_id) if session_id else None,
            turn_id=str(turn_id) if turn_id is not None else None,
        )

        if result.get("status") in {"ambiguous", "requires_confirmation"}:
            return ToolResult(
                success=False,
                error=result.get("status"),
                data=result,
                metadata={
                    "message": result.get("message", ""),
                    "confirmation_token": result.get("confirmation_token"),
                    "task_id": result.get("task_id"),
                },
            )

        if result.get("status") == "error":
            return ToolResult(
                success=False,
                error=result.get("error", "mutation_failed"),
                data=result,
                metadata={"message": result.get("message", "")},
            )

        return ToolResult(
            success=True,
            data=result,
            metadata={"message": result.get("message", "Tâche marquée comme terminée avec succès.")},
        )


class GetCoachingAdviceTool(AITool):
    name = "get_coaching_advice"
    description = (
        "Fournit des recommandations et conseils de coaching professionnel personnalisés "
        "adaptés au métier du collaborateur (vendeur, réceptionniste, technicien, retail, gestionnaire, support)."
    )
    input_schema = CoachingAdviceArgs
    required_permissions = ("ai:use",)
    read_only = True
    mutates = False
    agent_ids = frozenset({"voice", "coach", "central"})

    def __init__(self, session: Session) -> None:
        self._session = session

    async def run(self, context: ToolExecutionContext, arguments: CoachingAdviceArgs) -> ToolResult:
        ok, err, actor = _verify_coach_access(self._session, context, write=False)
        if not ok or actor is None:
            return ToolResult(success=False, error=err or "unauthorized")

        coach = EmployeeCoachService(self._session)
        locale = getattr(context, "locale", "fr-CA") or "fr-CA"
        advice = coach.get_coaching_advice(actor, topic=arguments.topic, locale=str(locale))

        return ToolResult(
            success=True,
            data=advice,
            metadata={"message": advice.get("title", "Conseils de coaching professionnel disponibles.")},
        )


__all__ = [
    "GetMyDailyBriefingTool",
    "GetMyTasksTool",
    "MarkMyTaskCompletedTool",
    "GetCoachingAdviceTool",
]
