"""Dépendances FastAPI établissant une identité multi-tenant de confiance."""

import hmac
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.app.core.permissions import permissions_for
from backend.app.config.settings import get_settings
from backend.app.database import get_db
from backend.app.models import AuthSession, User
from backend.app.services.account_notifications import (
    AccountNotifier,
    HTTPSAccountNotifier,
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
    if settings.email_provider == "https_api" and settings.email_delivery_configured:
        return HTTPSAccountNotifier(settings)
    if settings.email_delivery_configured:
        return SMTPAccountNotifier(settings)
    return LoggingAccountNotifier()


def get_auth_service(
    db: Session = Depends(get_db),
    notifier: AccountNotifier = Depends(get_account_notifier),
) -> AuthService:
    return AuthService(db, notifier)


def _verify_csrf(request: Request) -> None:
    """Valide les requêtes mutables authentifiées par cookie.

    Accepte :
    1. Sec-Fetch-Site: 'same-origin', 'same-site', ou 'none'
    2. Double-submit cookie : cookie 'avenqo_csrf' == header 'x-csrf-token'
    3. Header custom 'x-requested-with' ou 'x-avenqo-client'
    """
    sec_fetch_site = request.headers.get("sec-fetch-site")
    if sec_fetch_site in ("same-origin", "same-site", "none"):
        return

    csrf_cookie = request.cookies.get("avenqo_csrf")
    csrf_header = request.headers.get("x-csrf-token") or request.headers.get("x-xsrf-token")
    if csrf_cookie and csrf_header and hmac.compare_digest(csrf_cookie, csrf_header):
        return

    x_requested_with = request.headers.get("x-requested-with")
    if x_requested_with and x_requested_with.lower() in ("xmlhttprequest", "avenqo-web", "avenqo-flutter"):
        return

    if request.headers.get("x-avenqo-client"):
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Protection CSRF : requête refusée",
    )


def get_current_identity(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    service: AuthService = Depends(get_auth_service),
) -> CurrentIdentity:
    """Transforme le Bearer token ou le cookie HttpOnly en utilisateur et tenant vérifiés."""

    token: str | None = None
    is_cookie_auth = False

    if credentials is not None and credentials.scheme.lower() == "bearer":
        token = credentials.credentials
    elif "avenqo_access_token" in request.cookies:
        token = request.cookies["avenqo_access_token"]
        is_cookie_auth = True

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentification requise",
        )

    if is_cookie_auth and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        _verify_csrf(request)

    try:
        auth_session, user = service.authenticate(token)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    return CurrentIdentity(auth_session, user, token)


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