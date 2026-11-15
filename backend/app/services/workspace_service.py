"""Responsabilités, tâches, invitations et guidance personnelle — scopés au tenant."""

from __future__ import annotations

import secrets

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.permission_grants import (
    cap_grants,
    effective_permissions,
    encode_grants,
    grants_for_responsibility,
    tasks_for_responsibility,
)
from backend.app.core.security import generate_token, hash_password, hash_token
from backend.app.models.company_module import company_module_is_active
from backend.app.models import (
    Company,
    CompanyMembership,
    CompanyModule,
    EmployeeInvitation,
    EmployeeResponsibility,
    EmployeeTask,
    Module,
    User,
    UserRole,
)
from backend.app.config.settings import get_settings
from backend.app.services.account_notifications import AccountNotifier, mailbox_delivery
from backend.app.services.plan_limits_service import PlanLimitsService


class WorkspaceError(ValueError):
    pass


class MailNotConfigured(WorkspaceError):
    def __init__(self, missing: list[str]) -> None:
        self.missing = missing
        names = ", ".join(missing) or "SMTP_HOST"
        super().__init__(f"Livraison email impossible. Réglages manquants : {names}")


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
        can_see_all = "users:manage" in effective_permissions(actor)
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
        if "users:manage" not in effective_permissions(actor):
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
        if "users:manage" not in effective_permissions(actor) and target != actor.id:
            raise WorkspaceError("Permission insuffisante")
        query = query.where(EmployeeResponsibility.user_id == target).order_by(EmployeeResponsibility.created_at.desc())
        return list(self._session.scalars(query))

    def add_responsibility(self, actor: User, user_id: UUID, title: str, description: str | None) -> EmployeeResponsibility:
        if "users:manage" not in effective_permissions(actor):
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
        if mine or "users:manage" not in effective_permissions(actor) and actor.role not in {UserRole.MANAGER, UserRole.OWNER, UserRole.ADMIN}:
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
        if assignee_user_id != actor.id and "users:manage" not in effective_permissions(actor) and actor.role != UserRole.MANAGER:
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
        if task.assignee_user_id != actor.id and "users:manage" not in effective_permissions(actor):
            raise WorkspaceError("Permission insuffisante")
        task.status = "done"
        task.completed_at = datetime.now(timezone.utc)
        self._session.commit()
        return task

    def invite(self, actor: User, email: str, role: UserRole, job_title: str, department: str | None) -> EmployeeInvitation:
        if "users:manage" not in effective_permissions(actor):
            raise WorkspaceError("Permission insuffisante")
        if role == UserRole.OWNER:
            raise WorkspaceError("Le rôle propriétaire ne peut pas être attribué")
        PlanLimitsService(self._session).ensure_user_capacity(actor.company_id)
        ready, missing = mailbox_delivery(self._notifier, get_settings())
        if not ready or self._notifier is None or not hasattr(self._notifier, "send_transactional"):
            raise MailNotConfigured(missing)
        normalized = email.strip().lower()
        existing_user = self._session.scalar(select(User).where(User.email == normalized))
        if existing_user is not None and existing_user.company_id != actor.company_id:
            raise WorkspaceError("Cette adresse appartient déjà à une autre entreprise")
        if existing_user is not None and existing_user.role not in {UserRole.USER, UserRole.VIEWER, UserRole.ANALYST}:
            raise WorkspaceError(
                f"{existing_user.first_name} {existing_user.last_name} a déjà un accès avec cette adresse. "
                "Utilisez un autre courriel pour ajouter une autre personne."
            )
        granted = encode_grants(
            cap_grants(grants_for_responsibility(job_title, role), effective_permissions(actor))
        )
        existing = self._session.scalar(
            select(EmployeeInvitation).where(
                EmployeeInvitation.company_id == actor.company_id,
                EmployeeInvitation.email == normalized,
                EmployeeInvitation.accepted_at.is_(None),
                EmployeeInvitation.revoked_at.is_(None),
            )
        )
        raw = generate_token()
        code = f"{secrets.randbelow(90000000) + 10000000}"
        salt = secrets.token_hex(16)
        code_h = hash_token(f"{code}:{salt}")
        now = datetime.now(timezone.utc)
        if existing is None:
            invitation = EmployeeInvitation(
                company_id=actor.company_id,
                invited_by_user_id=actor.id,
                email=normalized,
                role=role.value,
                job_title=job_title.strip() or "Employee",
                department=department,
                permission_grants=granted,
                token_hash=hash_token(raw),
                code_hash=code_h,
                code_salt=salt,
                failed_attempts=0,
                expires_at=now + timedelta(hours=24),
            )
            self._session.add(invitation)
        else:
            invitation = existing
            invitation.invited_by_user_id = actor.id
            invitation.role = role.value
            invitation.job_title = job_title.strip() or invitation.job_title
            invitation.department = department
            invitation.permission_grants = granted
            invitation.token_hash = hash_token(raw)
            invitation.code_hash = code_h
            invitation.code_salt = salt
            invitation.failed_attempts = 0
            invitation.expires_at = now + timedelta(hours=24)
        self._session.flush()
        origin = get_settings().public_frontend_origin()
        link = f"{origin}/join?token={raw}"
        company_name = actor.company.name if actor.company is not None else "votre entreprise"
        title = invitation.job_title
        text_body = "\n".join(
            (
                f"Vous êtes invité à rejoindre {company_name} comme {title}.",
                "Ce code ouvre uniquement l'espace de cette entreprise.",
                "Entrez votre courriel, ce code, puis choisissez votre mot de passe.",
                link,
                f"Code d'accès: {code}",
            )
        )
        html_body = (
            f"<p>Vous êtes invité à rejoindre {company_name} comme {title}.</p>"
            "<p>Ce code ouvre uniquement l'espace de cette entreprise. "
            "Entrez votre courriel, le code, puis choisissez votre mot de passe.</p>"
            f'<p><a href="{link}">Ouvrir {company_name}</a></p>'
            f"<p>Code d'accès : <strong>{code}</strong></p>"
        )
        from backend.app.services.account_notifications import sandbox_mail_company_id, sandbox_mail_session

        company_token = sandbox_mail_company_id.set(str(actor.company_id))
        session_token = sandbox_mail_session.set(self._session)
        try:
            try:
                self._notifier.send_transactional(  # type: ignore[union-attr]
                    normalized,
                    "Invitation Avenqo",
                    text_body,
                    html_body,
                )
            except TypeError:
                self._notifier.send_transactional(  # type: ignore[union-attr]
                    normalized,
                    "Invitation Avenqo",
                    text_body,
                )
        except Exception:
            self._session.rollback()
            raise MailNotConfigured(missing) from None
        finally:
            sandbox_mail_company_id.reset(company_token)
            sandbox_mail_session.reset(session_token)
        self._session.commit()
        invitation._raw_token = raw  # type: ignore[attr-defined]
        invitation._raw_code = code  # type: ignore[attr-defined]
        return invitation


    def invite_bulk(
        self, actor: User, emails: list[str], role: UserRole, job_title: str, department: str | None
    ) -> list[EmployeeInvitation]:
        invitations = []
        for email in emails:
            if not email or not email.strip():
                continue
            invitations.append(self.invite(actor, email.strip(), role, job_title, department))
        return invitations

    def preview_invitation(
        self,
        token: str | None = None,
        *,
        code: str | None = None,
        email: str | None = None,
    ) -> dict[str, str]:
        invitation = self._find_invitation(token, code=code, email=email, consume_failure=False)
        self._assert_invitation_open(invitation)
        company = self._session.get(Company, invitation.company_id)
        member = self._session.scalar(select(User).where(User.email == invitation.email))
        same_company = member is not None and member.company_id == invitation.company_id
        return {
            "company_name": company.name if company is not None else "",
            "job_title": invitation.job_title,
            "department": invitation.department or "",
            "already_member": "yes" if same_company else "",
            "member_name": f"{member.first_name} {member.last_name}".strip() if same_company and member is not None else "",
            "member_title": member.job_title if same_company and member is not None else "",
        }

    def revoke_invitation(self, actor: User, invitation_id: UUID) -> EmployeeInvitation:
        if "users:manage" not in effective_permissions(actor):
            raise WorkspaceError("Permission insuffisante")
        invitation = self._session.get(EmployeeInvitation, invitation_id)
        if invitation is None or invitation.company_id != actor.company_id:
            raise WorkspaceError("Invitation introuvable")
        if invitation.accepted_at is not None:
            raise WorkspaceError("Cette invitation est déjà utilisée")
        invitation.revoked_at = datetime.now(timezone.utc)
        self._session.commit()
        return invitation

    def pending_invitations(self, actor: User) -> list[EmployeeInvitation]:
        if "users:manage" not in effective_permissions(actor):
            return []
        now = datetime.now(timezone.utc)
        rows = list(
            self._session.scalars(
                select(EmployeeInvitation).where(
                    EmployeeInvitation.company_id == actor.company_id,
                    EmployeeInvitation.accepted_at.is_(None),
                    EmployeeInvitation.revoked_at.is_(None),
                )
            )
        )
        open_rows = []
        for row in rows:
            expires = row.expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires > now:
                open_rows.append(row)
        return open_rows

    def accept_invitation(
        self,
        token: str | None,
        first_name: str,
        last_name: str,
        password: str,
        *,
        code: str | None = None,
        email: str | None = None,
    ) -> User:
        invitation = self._find_invitation(token, code=code, email=email, consume_failure=True)
        self._assert_invitation_open(invitation)
        try:
            locked = self._session.get(EmployeeInvitation, invitation.id, with_for_update=True)
        except Exception:
            self._session.rollback()
            invitation = self._find_invitation(token, code=code, email=email, consume_failure=False)
            locked = self._session.get(EmployeeInvitation, invitation.id)
        if locked is None:
            raise WorkspaceError("Invitation invalide ou expirée")
        self._assert_invitation_open(locked)
        now = datetime.now(timezone.utc)
        existing = self._session.scalar(select(User).where(User.email == locked.email))
        if existing is not None and existing.company_id != locked.company_id:
            raise WorkspaceError("Cette adresse appartient déjà à une autre entreprise")
        if existing is None:
            PlanLimitsService(self._session).ensure_user_capacity(locked.company_id, adding=0)
            user = User(
                company_id=locked.company_id,
                first_name=first_name.strip(),
                last_name=last_name.strip(),
                email=locked.email,
                password_hash=hash_password(password),
                role=UserRole(locked.role),
                job_title=locked.job_title,
                department=locked.department,
                permission_grants=locked.permission_grants
                or encode_grants(grants_for_responsibility(locked.job_title, locked.role)),
                is_active=True,
                email_verified_at=now,
            )
            self._session.add(user)
            self._session.flush()
            self._session.add(
                CompanyMembership(
                    user_id=user.id,
                    company_id=locked.company_id,
                    role=user.role,
                    is_active=True,
                )
            )
            self._assign_job_tasks(user, locked)
        else:
            if existing.company_id != locked.company_id:
                raise WorkspaceError("Cette adresse appartient déjà à une autre entreprise")
            if existing.role != UserRole.USER or existing.last_login is not None:
                raise WorkspaceError(
                    f"Ce courriel appartient déjà à {existing.first_name} {existing.last_name} dans cette entreprise. "
                    "Le code d'accès ne crée pas un autre employé. Utilisez le courriel de la personne."
                )
            existing.password_hash = hash_password(password)
            existing.first_name = first_name.strip() or existing.first_name
            existing.last_name = last_name.strip() or existing.last_name
            existing.role = UserRole(locked.role)
            existing.job_title = locked.job_title
            existing.department = locked.department
            existing.permission_grants = locked.permission_grants or encode_grants(
                grants_for_responsibility(locked.job_title, locked.role)
            )
            existing.is_active = True
            user = existing
            self._assign_job_tasks(user, locked)
            membership = self._session.scalar(
                select(CompanyMembership).where(
                    CompanyMembership.user_id == user.id,
                    CompanyMembership.company_id == locked.company_id,
                )
            )
            if membership is None:
                self._session.add(
                    CompanyMembership(
                        user_id=user.id,
                        company_id=locked.company_id,
                        role=user.role,
                        is_active=True,
                    )
                )
            else:
                membership.is_active = True
                membership.role = user.role
        locked.accepted_at = now
        try:
            self._session.commit()
        except IntegrityError:
            self._session.rollback()
            raise WorkspaceError("Invitation invalide ou expirée") from None
        return user

    def _assign_job_tasks(self, user: User, invitation: EmployeeInvitation) -> None:
        """Pose les tâches du poste dans l'entreprise qui a émis le code, et nulle part ailleurs."""

        if user.company_id != invitation.company_id:
            raise WorkspaceError("Le code d'accès ne correspond pas à cette entreprise")
        existing = set(
            self._session.scalars(
                select(EmployeeTask.title).where(
                    EmployeeTask.company_id == invitation.company_id,
                    EmployeeTask.assignee_user_id == user.id,
                )
            )
        )
        for title in tasks_for_responsibility(invitation.job_title):
            if title in existing:
                continue
            self._session.add(
                EmployeeTask(
                    company_id=invitation.company_id,
                    assignee_user_id=user.id,
                    created_by_user_id=invitation.invited_by_user_id,
                    title=title,
                    priority="medium",
                    status="open",
                )
            )

    def _find_invitation(
        self,
        token: str | None,
        *,
        code: str | None,
        email: str | None,
        consume_failure: bool,
    ) -> EmployeeInvitation:
        now = datetime.now(timezone.utc)
        if code and email:
            normalized_email = email.strip().lower()
            invitation = self._session.scalar(
                select(EmployeeInvitation)
                .where(EmployeeInvitation.email == normalized_email)
                .order_by(EmployeeInvitation.created_at.desc())
            )
            if invitation is None or invitation.accepted_at is not None or invitation.revoked_at is not None:
                raise WorkspaceError("Aucune invitation active trouvée pour cet email")
            if invitation.failed_attempts >= 5:
                invitation.revoked_at = now
                self._session.commit()
                raise WorkspaceError("Nombre maximal de tentatives dépassé. Invitation révoquée par sécurité.")
            expected_hash = hash_token(f"{code.strip()}:{invitation.code_salt}")
            if not secrets.compare_digest(invitation.code_hash or "", expected_hash):
                if consume_failure:
                    invitation.failed_attempts += 1
                    if invitation.failed_attempts >= 5:
                        invitation.revoked_at = now
                    self._session.commit()
                    remaining = max(0, 5 - invitation.failed_attempts)
                    raise WorkspaceError(f"Code d'invitation incorrect. {remaining} tentative(s) restante(s).")
                raise WorkspaceError("Invitation invalide ou expirée")
            return invitation
        if token:
            invitation = self._session.scalar(
                select(EmployeeInvitation).where(EmployeeInvitation.token_hash == hash_token(token))
            )
            if invitation is None:
                raise WorkspaceError("Invitation invalide ou expirée")
            return invitation
        raise WorkspaceError("Jeton ou code d'invitation requis")

    @staticmethod
    def _assert_invitation_open(invitation: EmployeeInvitation) -> None:
        now = datetime.now(timezone.utc)
        expires = invitation.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if invitation.accepted_at is not None or invitation.revoked_at is not None or expires <= now:
            raise WorkspaceError("Invitation invalide ou expirée")

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
        modules = [
            code
            for code in self._session.scalars(
                select(Module.code)
                .join(CompanyModule, CompanyModule.module_id == Module.id)
                .where(
                    CompanyModule.company_id == actor.company_id,
                    company_module_is_active(),
                )
            )
            if self._module_visible(actor, code)
        ]
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
            "company_name": actor.company.name if actor.company is not None else "",
            "permissions": list(effective_permissions(actor)),
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

    @staticmethod
    def _module_visible(actor: User, code: str) -> bool:
        held = set(effective_permissions(actor))
        if code == "crm":
            return bool({"crm:appointments:read", "crm:clients:read"} & held)
        if code == "accounting":
            return "accounting:read" in held
        if code == "marketing":
            return "marketing:read" in held
        if code == "retail":
            return "retail:read" in held
        if code == "voice":
            return "modules:manage" in held
        return "modules:manage" in held or "ai:use" in held

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
