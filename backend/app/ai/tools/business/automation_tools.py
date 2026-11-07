"""Workflow Automation tools for Central AI orchestration (Phase 8.1).

Enables Central AI to prepare automated workflows, request explicit confirmation,
and execute authorized automations safely.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4
from pydantic import Field
from sqlalchemy.orm import Session

from backend.app.ai.tools.base import AutomationAITool, ToolArguments
from backend.app.ai.tools.contracts import ToolExecutionContext, ToolResult
from backend.app.services.automation_service import AutomationError, AutomationService
from backend.app.models.user import User


class DraftAutomationWorkflowArgs(ToolArguments):
    name: str = Field(description="Nom descriptif du workflow (ex: 'Auto-confirmation RDV client').")
    trigger_type: str = Field(description="Événement déclencheur (ex: 'crm.appointment_created', 'document_uploaded', 'sale.created').")
    action_type: str = Field(description="Action à exécuter (ex: 'email.send_confirmation', 'crm.add_note', 'accounting.create_draft').")
    condition: dict[str, Any] = Field(default_factory=dict, description="Conditions de déclenchement (ex: {'status': 'confirmed'}).")
    action: dict[str, Any] = Field(default_factory=dict, description="Paramètres de l'action (ex: {'template': 'confirmation_standard'}).")
    confirmed: bool = Field(default=False, description="Doit valoir true UNIQUEMENT après validation explicite par l'utilisateur.")


class ExecuteAutomationWorkflowArgs(ToolArguments):
    workflow_id: str = Field(description="Identifiant UUID du workflow à exécuter.")
    idempotency_key: str = Field(description="Clé d'idempotence unique pour éviter les exécutions dupliquées.")
    payload: dict[str, Any] = Field(default_factory=dict, description="Données contextuelles de l'événement déclencheur.")


class DraftAutomationWorkflowTool(AutomationAITool):
    name = "draft_automation_workflow"
    description = (
        "Prépare un projet d'automatisation de workflow (déclencheur et action). "
        "Si confirmed=false, renvoie le projet détaillé pour confirmation humaine. "
        "Si confirmed=true, enregistre et active le workflow dans l'entreprise."
    )
    input_schema = DraftAutomationWorkflowArgs
    required_permissions = ("ai:use", "workflow:manage")
    confirmation_policy = "explicit_user_confirmation"
    confirmation_field = "confirmed"

    def __init__(self, session: Session) -> None:
        self._session = session

    async def run(self, context: ToolExecutionContext, arguments: DraftAutomationWorkflowArgs) -> ToolResult:
        if not arguments.confirmed:
            return ToolResult(
                success=True,
                data={
                    "status": "confirmation_required",
                    "workflow_name": arguments.name,
                    "trigger_type": arguments.trigger_type,
                    "action_type": arguments.action_type,
                    "condition": arguments.condition,
                    "action": arguments.action,
                    "requires_user_confirmation": True,
                    "message": f"Projet d'automatisation '{arguments.name}' prêt. Confirmez-vous sa création et son activation ?",
                },
                source_refs=("automation_workflows",),
            )

        actor = self._session.query(User).filter(User.id == context.tenant.user_id).first()
        if not actor:
            return ToolResult(success=False, error="Utilisateur introuvable")

        service = AutomationService(self._session)
        try:
            row = service.create_workflow(
                actor,
                name=arguments.name,
                trigger_type=arguments.trigger_type,
                action_type=arguments.action_type,
                condition=arguments.condition,
                action=arguments.action,
            )
        except AutomationError as exc:
            return ToolResult(success=False, error=str(exc))

        return ToolResult(
            success=True,
            data={
                "status": "confirmed",
                "workflow_id": str(row.id),
                "name": row.name,
                "is_enabled": row.is_enabled,
                "message": f"Workflow d'automatisation '{row.name}' créé et activé avec succès.",
            },
            source_refs=("automation_workflows",),
        )


class ExecuteAutomationWorkflowTool(AutomationAITool):
    name = "execute_automation_workflow"
    description = "Exécute manuellement ou sur événement un workflow d'automatisation autorisé."
    input_schema = ExecuteAutomationWorkflowArgs
    required_permissions = ("ai:use", "workflow:manage")

    def __init__(self, session: Session) -> None:
        self._session = session

    async def run(self, context: ToolExecutionContext, arguments: ExecuteAutomationWorkflowArgs) -> ToolResult:
        try:
            wf_uuid = UUID(arguments.workflow_id)
        except ValueError:
            return ToolResult(success=False, error="Format UUID de workflow invalide")

        actor = self._session.query(User).filter(User.id == context.tenant.user_id).first()
        if not actor:
            return ToolResult(success=False, error="Utilisateur introuvable")

        service = AutomationService(self._session)
        try:
            run = service.run(
                actor,
                wf_uuid,
                idempotency_key=arguments.idempotency_key,
                payload=arguments.payload,
            )
        except AutomationError as exc:
            return ToolResult(success=False, error=str(exc))

        return ToolResult(
            success=True,
            data={
                "run_id": str(run.id),
                "workflow_id": str(wf_uuid),
                "status": run.status,
                "detail": run.detail,
            },
            source_refs=("automation_runs",),
        )
