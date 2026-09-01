"""Routes HTTP de crÃ©ation et de sÃ©curisation des comptes Avenqo."""

from fastapi import APIRouter, Depends, HTTPException, status

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

    email_delivery_configured = get_settings().smtp_host is not None
    if verification_email_sent:
        message = "Compte créé. Vérifiez votre adresse email."
    else:
        message = "Compte créé. L'email de vérification n'a pas pu être envoyé. Vous pouvez demander un renvoi."
    return MessageResponse(
        message=message,
        email_delivery_configured=email_delivery_configured and verification_email_sent,
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
    service.resend_verification(str(request.email))
    return MessageResponse(message="Si le compte existe, un email a Ã©tÃ© envoyÃ©.")


@router.post(
    "/login",
    response_model=AuthResponse,
    dependencies=[Depends(rate_limit("auth_login", "rate_limit_auth_per_minute"))],
)
def login(
    request: LoginRequest,
    service: AuthService = Depends(get_auth_service),
) -> AuthResponse:
    try:
        result = service.login(str(request.email), request.password)
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
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
    request: RefreshTokenRequest,
    service: AuthService = Depends(get_auth_service),
) -> AuthResponse:
    try:
        result = service.refresh(request.refresh_token)
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
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
    identity: CurrentIdentity = Depends(get_current_identity),
    service: AuthService = Depends(get_auth_service),
) -> MessageResponse:
    service.logout(identity.raw_token)
    return MessageResponse(message="Session fermÃ©e.")


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
