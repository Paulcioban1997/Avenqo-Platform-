"""Avenqo AI Employee Performance Coach tools for Central AI orchestration.

Provides authenticated telephone callers with their personal daily shift briefing,
task progress inspection, task completion mutation, and role-adapted coaching advice.
Strictly requires authenticated staff identity (fail-closed if anonymous).
"""

from __future__ import annotations

from typing import Any
from pydantic import Field
from sqlalchemy.orm import Session

from backend.app.ai.tools.base import AITool, ToolArguments
from backend.app.ai.tools.contracts import ToolExecutionContext, ToolResult
from backend.app.models.user import User
from backend.app.services.employee_coach_service import EmployeeCoachService


class EmptyCoachArgs(ToolArguments):
    pass


class TaskStatusArgs(ToolArguments):
    status: str | None = Field(default=None, description="Filtre de statut : open, in_progress, done")


class CompleteTaskArgs(ToolArguments):
    task_identifier: str = Field(
        ...,
        description="Identifiant UUID de la tâche ou mot-clé caractéristique de son titre",
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
        if not context.tenant.user_id:
            return ToolResult(
                success=False,
                error="Le coaching employé requiert une authentification téléphonique par NIP préalable.",
            )

        actor = self._session.get(User, context.tenant.user_id)
        if actor is None or actor.company_id != context.tenant.company_id:
            return ToolResult(
                success=False,
                error="Collaborateur non trouvé ou non autorisé pour cette entreprise.",
            )

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
        if not context.tenant.user_id:
            return ToolResult(
                success=False,
                error="La consultation des tâches internes requiert une authentification préalable par NIP.",
            )

        actor = self._session.get(User, context.tenant.user_id)
        if actor is None or actor.company_id != context.tenant.company_id:
            return ToolResult(success=False, error="unauthorized")

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
        "par son identifiant UUID ou un mot-clé précis de son titre."
    )
    input_schema = CompleteTaskArgs
    required_permissions = ("ai:use",)
    read_only = False
    mutates = True
    agent_ids = frozenset({"voice", "coach", "central"})

    def __init__(self, session: Session) -> None:
        self._session = session

    async def run(self, context: ToolExecutionContext, arguments: CompleteTaskArgs) -> ToolResult:
        if not context.tenant.user_id:
            return ToolResult(
                success=False,
                error="La modification des tâches internes requiert une authentification par NIP.",
            )

        actor = self._session.get(User, context.tenant.user_id)
        if actor is None or actor.company_id != context.tenant.company_id:
            return ToolResult(success=False, error="unauthorized")

        coach = EmployeeCoachService(self._session)
        result = coach.complete_task(actor, arguments.task_identifier)

        if result.get("status") == "error":
            return ToolResult(
                success=False,
                error=result.get("message") or result.get("error") or "mutation_failed",
                data=result,
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
        if not context.tenant.user_id:
            return ToolResult(
                success=False,
                error="Les conseils de coaching personnalisés requièrent une authentification préalable par NIP.",
            )

        actor = self._session.get(User, context.tenant.user_id)
        if actor is None or actor.company_id != context.tenant.company_id:
            return ToolResult(success=False, error="unauthorized")

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
