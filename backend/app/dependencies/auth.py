"""Dépendances FastAPI établissant une identité multi-tenant de confiance."""

from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.app.core.permissions import permissions_for
from backend.app.config.settings import get_settings
from backend.app.database import get_db
from backend.app.models import AuthSession, User
from backend.app.services.account_notifications import (
    AccountNotifier,
    LoggingAccountNotifier,
    SMTPAccountNotifier,
)
from backend.app.services.auth_service import AuthenticationError, AuthService
from shared.ai_engine.contracts import TenantContext

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class CurrentIdentity:
    """Identité vérifiée utilisée par les routes protégées."""

    auth_session: AuthSession
    user: User
    raw_token: str


def get_account_notifier() -> AccountNotifier:
    settings = get_settings()
    if settings.smtp_host:
        return SMTPAccountNotifier(settings)
    return LoggingAccountNotifier()


def get_auth_service(
    db: Session = Depends(get_db),
    notifier: AccountNotifier = Depends(get_account_notifier),
) -> AuthService:
    return AuthService(db, notifier)


def get_current_identity(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    service: AuthService = Depends(get_auth_service),
) -> CurrentIdentity:
    """Transforme le Bearer token en utilisateur et tenant vérifiés."""

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentification requise",
        )
    try:
        auth_session, user = service.authenticate(credentials.credentials)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    return CurrentIdentity(auth_session, user, credentials.credentials)


def get_tenant_context(
    identity: CurrentIdentity = Depends(get_current_identity),
) -> TenantContext:
    """Construit le contexte AI Engine depuis l'identité authentifiée."""

    return TenantContext(company_id=identity.user.company_id)


def require_permission(permission: str) -> Callable[..., CurrentIdentity]:
    """Construit une dépendance refusant les rôles sans la permission demandée."""

    def dependency(
        identity: CurrentIdentity = Depends(get_current_identity),
    ) -> CurrentIdentity:
        if permission not in permissions_for(identity.user.role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission insuffisante",
            )
        return identity

    return dependency


def require_platform_admin(
    identity: CurrentIdentity = Depends(get_current_identity),
) -> CurrentIdentity:
    """Réserve l'accès aux comptes explicitement marqués `is_platform_admin`.

    Indépendant du rôle tenant (owner/admin/...) : un propriétaire ou
    administrateur d'entreprise n'obtient jamais automatiquement l'accès
    plateforme Avenqo.
    """

    if not identity.user.is_platform_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux administrateurs Avenqo",
        )
    return identity