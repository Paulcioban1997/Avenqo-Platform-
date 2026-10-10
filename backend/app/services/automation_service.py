"""Moteur d'automatisation minimal : déclencheur, condition, action, anti-doublon."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.models import AutomationRun, AutomationWorkflow, EmployeeTask, User


ALLOWED_TRIGGERS = {"manual", "task_overdue", "document_uploaded"}
ALLOWED_ACTIONS = {"create_task", "notify_owner"}


class AutomationError(ValueError):
    pass


class AutomationService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_workflows(self, company_id: UUID) -> list[AutomationWorkflow]:
        return list(
            self._session.scalars(
                select(AutomationWorkflow)
                .where(AutomationWorkflow.company_id == company_id)
                .order_by(AutomationWorkflow.created_at.desc())
            )
        )

    def create_workflow(
        self,
        actor: User,
        *,
        name: str,
        trigger_type: str,
        action_type: str,
        condition: dict,
        action: dict,
    ) -> AutomationWorkflow:
        if trigger_type not in ALLOWED_TRIGGERS or action_type not in ALLOWED_ACTIONS:
            raise AutomationError("Déclencheur ou action non pris en charge")
        row = AutomationWorkflow(
            company_id=actor.company_id,
            created_by_user_id=actor.id,
            name=name.strip(),
            trigger_type=trigger_type,
            action_type=action_type,
            condition_json=json.dumps(condition or {}),
            action_json=json.dumps(action or {}),
        )
        self._session.add(row)
        self._session.commit()
        return row

    def run(
        self,
        actor: User,
        workflow_id: UUID,
        *,
        idempotency_key: str,
        payload: dict | None = None,
    ) -> AutomationRun:
        workflow = self._session.scalar(
            select(AutomationWorkflow).where(
                AutomationWorkflow.id == workflow_id,
                AutomationWorkflow.company_id == actor.company_id,
            )
        )
        if workflow is None or not workflow.is_enabled:
            raise AutomationError("Automatisation introuvable ou désactivée")
        existing = self._session.scalar(
            select(AutomationRun).where(
                AutomationRun.company_id == actor.company_id,
                AutomationRun.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            return existing
        if not self._conditions_met(workflow, payload or {}):
            run = AutomationRun(
                company_id=actor.company_id,
                workflow_id=workflow.id,
                idempotency_key=idempotency_key,
                status="skipped",
                detail="Conditions non satisfaites",
                created_at=datetime.now(timezone.utc),
            )
            self._session.add(run)
            self._session.commit()
            return run
        detail = self._execute(actor, workflow)
        run = AutomationRun(
            company_id=actor.company_id,
            workflow_id=workflow.id,
            idempotency_key=idempotency_key,
            status="completed",
            detail=detail,
            created_at=datetime.now(timezone.utc),
        )
        workflow.last_run_at = run.created_at
        workflow.last_status = run.status
        self._session.add(run)
        try:
            self._session.commit()
        except IntegrityError:
            self._session.rollback()
            replay = self._session.scalar(
                select(AutomationRun).where(
                    AutomationRun.company_id == actor.company_id,
                    AutomationRun.idempotency_key == idempotency_key,
                )
            )
            if replay is None:
                raise
            return replay
        return run

    def _conditions_met(self, workflow: AutomationWorkflow, payload: dict) -> bool:
        condition = json.loads(workflow.condition_json or "{}")
        required = condition.get("equals") or {}
        return all(str(payload.get(key, "")) == str(value) for key, value in required.items())

    def _execute(self, actor: User, workflow: AutomationWorkflow) -> str:
        action = json.loads(workflow.action_json or "{}")
        if workflow.action_type == "create_task":
            title = str(action.get("title") or workflow.name)
            task = EmployeeTask(
                company_id=actor.company_id,
                assignee_user_id=UUID(str(action.get("assignee_user_id") or actor.id)),
                created_by_user_id=actor.id,
                title=title,
                description=str(action.get("description") or ""),
                priority=str(action.get("priority") or "medium"),
            )
            if task.assignee_user_id:
                owner = self._session.get(User, task.assignee_user_id)
                if owner is None or owner.company_id != actor.company_id:
                    raise AutomationError("Destinataire hors entreprise")
            self._session.add(task)
            return f"Tâche créée : {title}"
        return f"Notification interne : {workflow.name}"
