"""Routes HTTP de crÃ©ation et de sÃ©curisation des comptes Avenqo."""

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from backend.app.config.settings import get_settings
from backend.app.core.permissions import permissions_for
from backend.app.core.rate_limit import rate_limit
from backend.app.dependencies.auth import CurrentIdentity, get_auth_service, get_current_identity
from backend.app.models import Company, User
from backend.app.models.base import OnboardingStatus
from backend.app.schemas.auth import (
    AuthResponse,
    CompanyResponse,
    CurrentAccountResponse,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RefreshTokenRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenRequest,
    UserResponse,
)
from backend.app.services.auth_service import (
    AuthenticationError,
    AuthService,
    ConflictError,
    InvalidModuleSelection,
)

router = APIRouter(prefix="/auth", tags=["authentication"])


def _user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        company_id=user.company_id,
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
        role=user.role,
        permissions=permissions_for(user.role),
        is_active=user.is_active,
        is_platform_admin=user.is_platform_admin,
        email_verified_at=user.email_verified_at,
    )


def _company_response(company: Company) -> CompanyResponse:
    onboarding_status = company.onboarding.status if company.onboarding else OnboardingStatus.PENDING
    return CompanyResponse(
        id=company.id,
        name=company.name,
        slug=company.slug,
        subscription_plan=company.subscription_plan,
        onboarding_status=onboarding_status.value,
        billing_email=company.billing_email,
        country=company.country,
        preferred_language=company.preferred_language,
        currency_code=getattr(company, "currency_code", None),
        timezone=company.timezone,
    )


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    settings = get_settings()
    is_secure = settings.is_secure_cookie
    access_max_age = int(settings.auth_access_minutes * 60)
    refresh_max_age = int(settings.auth_refresh_days * 86400)

    # 1. Access token : HttpOnly, Secure en staging/prod HTTPS, SameSite=Lax, Path=/
    response.set_cookie(
        key="avenqo_access_token",
        value=access_token,
        max_age=access_max_age,
        httponly=True,
        secure=is_secure,
        samesite="lax",
        path="/",
    )

    # 2. Refresh token : HttpOnly, Secure en staging/prod HTTPS, SameSite=Strict, Path=/api/v1/auth
    response.set_cookie(
        key="avenqo_refresh_token",
        value=refresh_token,
        max_age=refresh_max_age,
        httponly=True,
        secure=is_secure,
        samesite="strict",
        path="/api/v1/auth",
    )

    # 3. Cookie CSRF pour validation double-submit
    csrf_token = secrets.token_urlsafe(32)
    response.set_cookie(
        key="avenqo_csrf",
        value=csrf_token,
        max_age=refresh_max_age,
        httponly=False,
        secure=is_secure,
        samesite="lax",
        path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(key="avenqo_access_token", path="/")
    response.delete_cookie(key="avenqo_refresh_token", path="/api/v1/auth")
    response.delete_cookie(key="avenqo_refresh_token", path="/")
    response.delete_cookie(key="avenqo_csrf", path="/")


@router.post(
    "/register",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("auth_register", "rate_limit_auth_per_minute"))],
)
def register(
    request: RegisterRequest,
    service: AuthService = Depends(get_auth_service),
) -> MessageResponse:
    """Crée atomiquement une organisation et son propriétaire."""

    try:
        _, _, verification_email_sent = service.register(request)
    except ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except InvalidModuleSelection as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if verification_email_sent:
        message = "Compte créé. Vérifiez votre adresse email."
    else:
        message = "Compte créé. L'email de vérification n'a pas pu être envoyé. Vous pouvez demander un renvoi."
    return MessageResponse(
        message=message,
        email_delivery_configured=verification_email_sent,
    )


@router.post("/verify-email", response_model=MessageResponse)
@router.post("/email/verify", response_model=MessageResponse)
def verify_email(
    request: TokenRequest,
    service: AuthService = Depends(get_auth_service),
) -> MessageResponse:
    try:
        service.verify_email(request.token)
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return MessageResponse(message="Adresse email vÃ©rifiÃ©e.")


@router.post(
    "/resend-verification",
    response_model=MessageResponse,
    dependencies=[Depends(rate_limit("auth_email_resend", "rate_limit_auth_per_minute"))],
)
@router.post(
    "/email/resend",
    response_model=MessageResponse,
    dependencies=[Depends(rate_limit("auth_email_resend", "rate_limit_auth_per_minute"))],
)
def resend_verification(
    request: ForgotPasswordRequest,
    service: AuthService = Depends(get_auth_service),
) -> MessageResponse:
    email_delivery_configured = service.resend_verification(str(request.email))
    message = (
        "Si le compte existe, un email a été envoyé."
        if email_delivery_configured
        else "La livraison des emails est temporairement indisponible. Contactez le support."
    )
    return MessageResponse(
        message=message,
        email_delivery_configured=email_delivery_configured,
    )


@router.post(
    "/login",
    response_model=AuthResponse,
    dependencies=[Depends(rate_limit("auth_login", "rate_limit_auth_per_minute"))],
)
def login(
    request: LoginRequest,
    response: Response,
    service: AuthService = Depends(get_auth_service),
) -> AuthResponse:
    try:
        result = service.login(str(request.email), request.password)
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    _set_auth_cookies(response, result.access_token, result.refresh_token)
    return AuthResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        access_expires_at=result.access_expires_at,
        refresh_expires_at=result.refresh_expires_at,
        user=_user_response(result.user),
        company=_company_response(result.user.company),
    )


@router.post("/refresh", response_model=AuthResponse)
def refresh(
    http_request: Request,
    response: Response,
    payload: RefreshTokenRequest | None = None,
    service: AuthService = Depends(get_auth_service),
) -> AuthResponse:
    refresh_token = (
        payload.refresh_token
        if payload and payload.refresh_token
        else http_request.cookies.get("avenqo_refresh_token")
    )
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token requis")
    try:
        result = service.refresh(refresh_token)
    except AuthenticationError as exc:
        _clear_auth_cookies(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    _set_auth_cookies(response, result.access_token, result.refresh_token)
    return AuthResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        access_expires_at=result.access_expires_at,
        refresh_expires_at=result.refresh_expires_at,
        user=_user_response(result.user),
        company=_company_response(result.user.company),
    )


@router.get("/me", response_model=CurrentAccountResponse)
def me(identity: CurrentIdentity = Depends(get_current_identity)) -> CurrentAccountResponse:
    return CurrentAccountResponse(
        user=_user_response(identity.user),
        company=_company_response(identity.user.company),
    )


@router.post("/logout", response_model=MessageResponse)
def logout(
    response: Response,
    identity: CurrentIdentity = Depends(get_current_identity),
    service: AuthService = Depends(get_auth_service),
) -> MessageResponse:
    service.logout(identity.raw_token)
    _clear_auth_cookies(response)
    return MessageResponse(message="Session fermée.")


@router.post(
    "/password/forgot",
    response_model=MessageResponse,
    dependencies=[Depends(rate_limit("auth_password_forgot", "rate_limit_auth_per_minute"))],
)
def forgot_password(
    request: ForgotPasswordRequest,
    service: AuthService = Depends(get_auth_service),
) -> MessageResponse:
    service.forgot_password(str(request.email))
    return MessageResponse(message="Si le compte existe, un email a Ã©tÃ© envoyÃ©.")


@router.post(
    "/password/reset",
    response_model=MessageResponse,
    dependencies=[Depends(rate_limit("auth_password_reset", "rate_limit_auth_per_minute"))],
)
def reset_password(
    request: ResetPasswordRequest,
    service: AuthService = Depends(get_auth_service),
) -> MessageResponse:
    try:
        service.reset_password(request.token, request.new_password)
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return MessageResponse(message="Mot de passe modifiÃ©. Reconnectez-vous.")
