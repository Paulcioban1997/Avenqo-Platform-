"""Responsabilités, tâches, invitations et guidance personnelle — scopés au tenant."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.permissions import permissions_for
from backend.app.core.security import generate_token, hash_password, hash_token
from backend.app.models import (
    Company,
    CompanyModule,
    EmployeeInvitation,
    EmployeeResponsibility,
    EmployeeTask,
    Module,
    User,
    UserRole,
)
from backend.app.models.base import CompanyModuleStatus
from backend.app.services.account_notifications import AccountNotifier
from backend.app.services.plan_limits_service import PlanLimitsService


class WorkspaceError(ValueError):
    pass


class WorkspaceService:
    def __init__(self, session: Session, notifier: AccountNotifier | None = None) -> None:
        self._session = session
        self._notifier = notifier

    def _user_in_company(self, company_id: UUID, user_id: UUID) -> User:
        user = self._session.scalar(select(User).where(User.id == user_id, User.company_id == company_id))
        if user is None:
            raise WorkspaceError("Employé introuvable dans cette entreprise")
        return user

    def list_team(self, actor: User) -> list[dict]:
        users = list(
            self._session.scalars(
                select(User).where(User.company_id == actor.company_id).order_by(User.first_name, User.last_name)
            )
        )
        responsibilities = list(
            self._session.scalars(
                select(EmployeeResponsibility).where(EmployeeResponsibility.company_id == actor.company_id)
            )
        )
        by_user: dict[UUID, list[EmployeeResponsibility]] = {}
        for row in responsibilities:
            by_user.setdefault(row.user_id, []).append(row)
        can_see_all = "users:manage" in permissions_for(actor.role)
        visible = users if can_see_all else [user for user in users if user.id == actor.id or user.role in {UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER}]
        return [self._team_card(user, by_user.get(user.id, [])) for user in visible]

    def org_chart(self, actor: User) -> dict:
        company = self._session.get(Company, actor.company_id)
        members = self.list_team(actor)
        departments: dict[str, list[dict]] = {}
        for member in members:
            departments.setdefault(member.get("department") or "Sans département", []).append(member)
        return {
            "company_id": str(actor.company_id),
            "company_name": company.name if company else "",
            "departments": [
                {"name": name, "members": people} for name, people in sorted(departments.items())
            ],
        }

    def assign_profile(self, actor: User, employee_id: UUID, *, job_title: str | None, department: str | None) -> User:
        if "users:manage" not in permissions_for(actor.role):
            raise WorkspaceError("Permission insuffisante")
        employee = self._user_in_company(actor.company_id, employee_id)
        if job_title is not None:
            employee.job_title = job_title.strip() or employee.job_title
        if department is not None:
            employee.department = department.strip() or None
        self._session.commit()
        return employee

    def list_responsibilities(self, actor: User, user_id: UUID | None = None) -> list[EmployeeResponsibility]:
        query = select(EmployeeResponsibility).where(EmployeeResponsibility.company_id == actor.company_id)
        target = user_id or actor.id
        if "users:manage" not in permissions_for(actor.role) and target != actor.id:
            raise WorkspaceError("Permission insuffisante")
        query = query.where(EmployeeResponsibility.user_id == target).order_by(EmployeeResponsibility.created_at.desc())
        return list(self._session.scalars(query))

    def add_responsibility(self, actor: User, user_id: UUID, title: str, description: str | None) -> EmployeeResponsibility:
        if "users:manage" not in permissions_for(actor.role):
            raise WorkspaceError("Permission insuffisante")
        self._user_in_company(actor.company_id, user_id)
        row = EmployeeResponsibility(
            company_id=actor.company_id,
            user_id=user_id,
            title=title.strip(),
            description=(description or "").strip() or None,
            assigned_by_user_id=actor.id,
        )
        self._session.add(row)
        self._session.commit()
        return row

    def list_tasks(self, actor: User, *, mine: bool = False) -> list[EmployeeTask]:
        query = select(EmployeeTask).where(EmployeeTask.company_id == actor.company_id)
        if mine or "users:manage" not in permissions_for(actor.role) and actor.role not in {UserRole.MANAGER, UserRole.OWNER, UserRole.ADMIN}:
            query = query.where(EmployeeTask.assignee_user_id == actor.id)
        return list(self._session.scalars(query.order_by(EmployeeTask.due_at.is_(None), EmployeeTask.due_at, EmployeeTask.created_at)))

    def create_task(
        self,
        actor: User,
        *,
        assignee_user_id: UUID,
        title: str,
        description: str | None,
        priority: str,
        due_at: datetime | None,
    ) -> EmployeeTask:
        if actor.role == UserRole.VIEWER:
            raise WorkspaceError("Permission insuffisante")
        self._user_in_company(actor.company_id, assignee_user_id)
        if assignee_user_id != actor.id and "users:manage" not in permissions_for(actor.role) and actor.role != UserRole.MANAGER:
            raise WorkspaceError("Vous ne pouvez attribuer une tâche qu'à vous-même")
        row = EmployeeTask(
            company_id=actor.company_id,
            assignee_user_id=assignee_user_id,
            created_by_user_id=actor.id,
            title=title.strip(),
            description=(description or "").strip() or None,
            priority=priority if priority in {"low", "medium", "high"} else "medium",
            due_at=due_at,
        )
        self._session.add(row)
        self._session.commit()
        return row

    def complete_task(self, actor: User, task_id: UUID) -> EmployeeTask:
        task = self._session.scalar(
            select(EmployeeTask).where(EmployeeTask.id == task_id, EmployeeTask.company_id == actor.company_id)
        )
        if task is None:
            raise WorkspaceError("Tâche introuvable")
        if task.assignee_user_id != actor.id and "users:manage" not in permissions_for(actor.role):
            raise WorkspaceError("Permission insuffisante")
        task.status = "done"
        task.completed_at = datetime.now(timezone.utc)
        self._session.commit()
        return task

    def invite(self, actor: User, email: str, role: UserRole, job_title: str, department: str | None) -> EmployeeInvitation:
        if "users:manage" not in permissions_for(actor.role):
            raise WorkspaceError("Permission insuffisante")
        if role == UserRole.OWNER:
            raise WorkspaceError("Le rôle propriétaire ne peut pas être attribué")
        PlanLimitsService(self._session).ensure_user_capacity(actor.company_id)
        normalized = email.strip().lower()
        if self._session.scalar(select(User.id).where(User.email == normalized)):
            raise WorkspaceError("Un compte utilise déjà cet email")
        existing = self._session.scalar(
            select(EmployeeInvitation).where(
                EmployeeInvitation.company_id == actor.company_id,
                EmployeeInvitation.email == normalized,
                EmployeeInvitation.accepted_at.is_(None),
                EmployeeInvitation.revoked_at.is_(None),
            )
        )
        if existing is not None:
            raise WorkspaceError("Une invitation est déjà en cours pour cet email")
        raw = generate_token()
        now = datetime.now(timezone.utc)
        invitation = EmployeeInvitation(
            company_id=actor.company_id,
            invited_by_user_id=actor.id,
            email=normalized,
            role=role.value,
            job_title=job_title.strip() or "Employee",
            department=department,
            token_hash=hash_token(raw),
            expires_at=now + timedelta(days=7),
        )
        self._session.add(invitation)
        self._session.commit()
        if self._notifier is not None and getattr(self._notifier, "email_delivery_configured", False):
            send = getattr(self._notifier, "send_email_verification", None)
            if send:
                send(normalized, raw)
        invitation._raw_token = raw  # type: ignore[attr-defined]
        return invitation

    def accept_invitation(self, token: str, first_name: str, last_name: str, password: str) -> User:
        invitation = self._session.scalar(
            select(EmployeeInvitation).where(EmployeeInvitation.token_hash == hash_token(token))
        )
        now = datetime.now(timezone.utc)
        expires = invitation.expires_at if invitation is not None else now
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if (
            invitation is None
            or invitation.accepted_at is not None
            or invitation.revoked_at is not None
            or expires <= now
        ):
            raise WorkspaceError("Invitation invalide ou expirée")
        PlanLimitsService(self._session).ensure_user_capacity(invitation.company_id, adding=0)
        user = User(
            company_id=invitation.company_id,
            first_name=first_name.strip(),
            last_name=last_name.strip(),
            email=invitation.email,
            password_hash=hash_password(password),
            role=UserRole(invitation.role),
            job_title=invitation.job_title,
            department=invitation.department,
            is_active=True,
            email_verified_at=now,
        )
        self._session.add(user)
        invitation.accepted_at = now
        self._session.commit()
        return user

    def personal_briefing(self, actor: User) -> dict:
        now = datetime.now(timezone.utc)
        tasks = self.list_tasks(actor, mine=True)
        open_tasks = [task for task in tasks if task.status != "done"]
        overdue = [task for task in open_tasks if task.due_at is not None and task.due_at < now]
        due_today = [
            task
            for task in open_tasks
            if task.due_at is not None and task.due_at.date() == now.date()
        ]
        modules = list(
            self._session.scalars(
                select(Module.code)
                .join(CompanyModule, CompanyModule.module_id == Module.id)
                .where(
                    CompanyModule.company_id == actor.company_id,
                    CompanyModule.status == CompanyModuleStatus.ACTIVE,
                )
            )
        )
        responsibilities = self.list_responsibilities(actor, actor.id)
        recommendations = []
        if overdue:
            recommendations.append(f"{len(overdue)} tâche(s) en retard à traiter en priorité.")
        if due_today:
            recommendations.append(f"{len(due_today)} échéance(s) aujourd'hui.")
        if not responsibilities and actor.role != UserRole.OWNER:
            recommendations.append("Aucune responsabilité n'est encore attribuée. Demandez-les à votre gestionnaire.")
        if not modules:
            recommendations.append("Aucun module métier n'est encore activé pour cette entreprise.")
        return {
            "user_id": str(actor.id),
            "company_id": str(actor.company_id),
            "first_name": actor.first_name,
            "job_title": actor.job_title,
            "department": actor.department,
            "role": actor.role.value,
            "permissions": list(permissions_for(actor.role)),
            "modules": modules,
            "responsibilities": [
                {"id": str(row.id), "title": row.title, "description": row.description} for row in responsibilities
            ],
            "open_tasks": [self._task_payload(task) for task in open_tasks],
            "overdue_tasks": [self._task_payload(task) for task in overdue],
            "today_tasks": [self._task_payload(task) for task in due_today],
            "recommendations": recommendations,
            "generated_at": now.isoformat(),
        }

    def answer_question(self, actor: User, question: str, *, confirm_token: str | None = None) -> dict:
        briefing = self.personal_briefing(actor)
        text = (question or "").strip()
        if len(text) < 3:
            raise WorkspaceError("Question trop courte")
        lowered = text.lower()
        modules = set(briefing["modules"])
        if any(word in lowered for word in ("rendez-vous", "rdv", "appointment", "calendar")):
            appointments = self._today_appointments(actor) if "crm" in modules else []
            return {
                "intent": "today_appointments",
                "invented": False,
                "answer": (
                    f"{len(appointments)} rendez-vous aujourd'hui."
                    if appointments
                    else "Aucun rendez-vous confirmé aujourd'hui dans le CRM."
                ),
                "data": appointments,
                "requires_confirmation": False,
            }
        if any(word in lowered for word in ("tâche", "tache", "task", "priorit")):
            overdue = briefing["overdue_tasks"]
            today = briefing["today_tasks"]
            return {
                "intent": "priority_tasks",
                "invented": False,
                "answer": (
                    f"{len(overdue)} tâche(s) en retard, {len(today)} échéance(s) aujourd'hui."
                    if overdue or today
                    else "Aucune tâche prioritaire n'est enregistrée pour vous."
                ),
                "data": {"overdue": overdue, "today": today, "open": briefing["open_tasks"]},
                "requires_confirmation": False,
            }
        if any(word in lowered for word in ("vente", "sales", "chiffre")):
            if "accounting" not in modules and "retail" not in modules:
                return {
                    "intent": "weekly_sales",
                    "invented": False,
                    "answer": "Les modules Retail ou Comptabilité ne sont pas activés pour cette entreprise.",
                    "data": [],
                    "requires_confirmation": False,
                }
            sales = self._week_sales(actor)
            return {
                "intent": "weekly_sales",
                "invented": False,
                "answer": (
                    f"Ventes confirmées cette semaine : {sales['total']} {sales['currency']}."
                    if sales["count"]
                    else "Aucune vente confirmée n'est enregistrée pour cette semaine."
                ),
                "data": sales,
                "requires_confirmation": False,
            }
        if any(word in lowered for word in ("rapport", "report", "gestionnaire", "manager")):
            return {
                "intent": "manager_report",
                "invented": False,
                "answer": "Rapport compilé à partir des tâches, responsabilités et modules réellement actifs.",
                "data": briefing,
                "requires_confirmation": False,
            }
        return {
            "intent": "unknown",
            "invented": False,
            "answer": "Je ne peux répondre qu'avec les rendez-vous, tâches, ventes confirmées ou un rapport de briefing. Aucune donnée n'a été inventée.",
            "data": {"permissions": briefing["permissions"], "modules": briefing["modules"]},
            "requires_confirmation": False,
        }

    def _today_appointments(self, actor: User) -> list[dict]:
        from backend.app.models.crm import CRMAppointment

        now = datetime.now(timezone.utc)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        rows = list(
            self._session.scalars(
                select(CRMAppointment).where(
                    CRMAppointment.company_id == actor.company_id,
                    CRMAppointment.is_deleted.is_(False),
                    CRMAppointment.start_time >= start,
                    CRMAppointment.start_time < end,
                )
            )
        )
        return [
            {
                "id": str(row.id),
                "title": row.title,
                "start_time": row.start_time.isoformat() if row.start_time else None,
                "status": row.status,
            }
            for row in rows
        ]

    def _week_sales(self, actor: User) -> dict:
        from backend.app.models.accounting import AccountingTransaction

        now = datetime.now(timezone.utc)
        start = now - timedelta(days=7)
        rows = list(
            self._session.scalars(
                select(AccountingTransaction).where(
                    AccountingTransaction.company_id == actor.company_id,
                    AccountingTransaction.transaction_type == "revenue",
                    AccountingTransaction.is_confirmed.is_(True),
                    AccountingTransaction.transaction_date >= start,
                )
            )
        )
        total = round(sum(row.amount for row in rows), 2)
        currency = rows[0].currency if rows else (actor.company.currency_code if actor.company else "CAD")
        return {"count": len(rows), "total": total, "currency": currency or "CAD"}

    def _team_card(self, user: User, responsibilities: list[EmployeeResponsibility]) -> dict:
        return {
            "id": str(user.id),
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "role": user.role.value,
            "job_title": user.job_title,
            "department": user.department,
            "is_active": user.is_active,
            "responsibilities": [row.title for row in responsibilities],
        }

    @staticmethod
    def _task_payload(task: EmployeeTask) -> dict:
        return {
            "id": str(task.id),
            "title": task.title,
            "description": task.description,
            "priority": task.priority,
            "status": task.status,
            "due_at": task.due_at.isoformat() if task.due_at else None,
            "assignee_user_id": str(task.assignee_user_id),
        }
