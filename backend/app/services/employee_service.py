"""Cas d'usage de gestion des employés, toujours limités au tenant courant."""

from datetime import datetime, timedelta, timezone
from uuid import UUID # UUID est utilisé pour les identifiants d'employés et de tokens

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.security import generate_token, hash_password, hash_token
from backend.app.models import AccountToken, AccountTokenPurpose, User, UserRole
from backend.app.schemas.employees import EmployeeCreateRequest, EmployeeUpdateRequest
from backend.app.services.account_notifications import AccountNotifier


class EmployeeConflictError(ValueError):
    pass


class EmployeeNotFoundError(ValueError):
    pass


class EmployeePermissionError(ValueError):
    pass


class EmployeeService:
    """Administre les employés sans accepter de company_id fourni par le client."""

    def __init__(self, session: Session, notifier: AccountNotifier) -> None:
        self._session = session
        self._notifier = notifier

    def list(self, actor: User) -> list[User]:
        return list(self._session.scalars(
            select(User)
            .where(User.company_id == actor.company_id)
            .order_by(User.first_name, User.last_name)
        ))

    def create(self, actor: User, request: EmployeeCreateRequest) -> User:
        self._ensure_assignable_role(actor, request.role)
        email = str(request.email).strip().lower()
        if self._session.scalar(select(User.id).where(User.email == email)):
            raise EmployeeConflictError("Un compte utilise déjà cet email")

        employee = User(
            company_id=actor.company_id,
            first_name=request.first_name.strip(),
            last_name=request.last_name.strip(),
            email=email,
            password_hash=hash_password(request.password),
            role=request.role,
            is_active=True,
        )
        self._session.add(employee)
        self._session.flush()
        raw_token = generate_token()
        now = datetime.now(timezone.utc)
        self._session.add(AccountToken(
            user=employee,
            purpose=AccountTokenPurpose.EMAIL_VERIFICATION,
            token_hash=hash_token(raw_token),
            created_at=now,
            expires_at=now + timedelta(hours=24),
        ))
        self._session.commit()
        self._notifier.send_email_verification(employee.email, raw_token)
        return employee

    def update(self, actor: User, employee_id: UUID, request: EmployeeUpdateRequest) -> User:
        employee = self._session.scalar(select(User).where(
            User.id == employee_id,
            User.company_id == actor.company_id,
        ))
        if employee is None:
            raise EmployeeNotFoundError("Employé introuvable")
        if employee.role == UserRole.OWNER:
            raise EmployeePermissionError("Le propriétaire ne peut pas être modifié ici")
        if actor.role == UserRole.ADMIN and employee.role == UserRole.ADMIN:
            raise EmployeePermissionError("Seul le propriétaire peut modifier un administrateur")
        if request.role is not None:
            self._ensure_assignable_role(actor, request.role)
            employee.role = request.role
        if request.first_name is not None:
            employee.first_name = request.first_name.strip()
        if request.last_name is not None:
            employee.last_name = request.last_name.strip()
        if request.is_active is not None:
            if employee.id == actor.id and not request.is_active:
                raise EmployeePermissionError("Vous ne pouvez pas désactiver votre propre compte")
            employee.is_active = request.is_active
            if not request.is_active:
                now = datetime.now(timezone.utc)
                for auth_session in employee.auth_sessions:
                    if auth_session.revoked_at is None:
                        auth_session.revoked_at = now
        self._session.commit()
        return employee

    @staticmethod
    def _ensure_assignable_role(actor: User, role: UserRole) -> None:
        if role == UserRole.OWNER:
            raise EmployeePermissionError("Le rôle propriétaire ne peut pas être attribué")
        if role == UserRole.ADMIN and actor.role != UserRole.OWNER:
            raise EmployeePermissionError("Seul le propriétaire peut attribuer le rôle administrateur")