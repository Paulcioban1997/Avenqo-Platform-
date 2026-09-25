"""Routes HTTP de crÃ©ation et de sÃ©curisation des comptes Avenqo."""

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.config.settings import get_settings
from backend.app.core.permissions import permissions_for
from backend.app.core.rate_limit import rate_limit
from backend.app.core.security import create_access_token
from backend.app.database import get_db
from backend.app.dependencies.auth import CurrentIdentity, get_auth_service, get_current_identity
from backend.app.models import AuditLogEntry, Company, CompanyMembership, User
from backend.app.models.base import CompanyStatus, OnboardingStatus
from backend.app.schemas.auth import (
    AuthResponse,
    CompanyResponse,
    CurrentAccountResponse,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    OrganizationMembershipResponse,
    RefreshTokenRequest,
    RegisterRequest,
    ResetPasswordRequest,
    SwitchTenantRequest,
    TokenRequest,
    UserResponse,
    VerifyEmailResponse,
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
        job_title=getattr(user, "job_title", "Owner"),
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


@router.post("/verify-email", response_model=VerifyEmailResponse)
@router.post("/email/verify", response_model=VerifyEmailResponse)
def verify_email(
    request: TokenRequest,
    response: Response,
    service: AuthService = Depends(get_auth_service),
    db: Session = Depends(get_db),
) -> VerifyEmailResponse:
    try:
        user = service.verify_email(request.token)
        result = service._create_auth_session(user)
        _set_auth_cookies(response, result.access_token, result.refresh_token)
        return VerifyEmailResponse(
            message="Adresse email vérifiée.",
            access_token=result.access_token,
            refresh_token=result.refresh_token,
            token_type="bearer",
            access_expires_at=result.access_expires_at,
            refresh_expires_at=result.refresh_expires_at,
            user=_user_response(result.user),
            company=_company_response(result.user.company),
            organizations=_get_user_organizations(db, result.user),
        )
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


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


def _get_user_organizations(db: Session, user: User) -> list[OrganizationMembershipResponse]:
    """Retourne la liste des organisations autorisées pour l'utilisateur.
    Pour un SUPER_ADMIN (is_platform_admin=True) : toutes les entreprises actives.
    Pour un utilisateur standard : son entreprise principale + ses adhésions actives."""
    if user.is_platform_admin:
        all_companies = db.scalars(
            select(Company)
            .where(Company.status == CompanyStatus.ACTIVE)
            .order_by(Company.name)
        ).all()
        return [
            OrganizationMembershipResponse(
                id=c.id,
                name=c.name,
                slug=c.slug,
                subscription_plan=c.subscription_plan,
                role="SUPER_ADMIN",
                is_active=True,
                is_current=(c.id == user.company_id),
            )
            for c in all_companies
        ]

    memberships_dict: dict[UUID, OrganizationMembershipResponse] = {}
    if user.company and user.company.status == CompanyStatus.ACTIVE:
        role_str = user.role.value if hasattr(user.role, "value") else str(user.role)
        memberships_dict[user.company.id] = OrganizationMembershipResponse(
            id=user.company.id,
            name=user.company.name,
            slug=user.company.slug,
            subscription_plan=user.company.subscription_plan,
            role=role_str,
            is_active=True,
            is_current=True,
        )

    extra_memberships = db.scalars(
        select(CompanyMembership)
        .where(
            CompanyMembership.user_id == user.id,
            CompanyMembership.is_active == True,
        )
    ).all()

    for m in extra_memberships:
        comp = db.get(Company, m.company_id)
        if comp and comp.status == CompanyStatus.ACTIVE:
            is_cur = (comp.id == user.company_id)
            m_role_str = m.role.value if hasattr(m.role, "value") else str(m.role)
            memberships_dict[comp.id] = OrganizationMembershipResponse(
                id=comp.id,
                name=comp.name,
                slug=comp.slug,
                subscription_plan=comp.subscription_plan,
                role=m_role_str,
                is_active=m.is_active,
                is_current=is_cur,
            )

    return list(memberships_dict.values())


@router.get("/me", response_model=CurrentAccountResponse)
def me(
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> CurrentAccountResponse:
    orgs = _get_user_organizations(db, identity.user)
    return CurrentAccountResponse(
        user=_user_response(identity.user),
        company=_company_response(identity.user.company),
        organizations=orgs,
    )


@router.get("/organizations", response_model=list[OrganizationMembershipResponse])
def get_organizations(
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> list[OrganizationMembershipResponse]:
    return _get_user_organizations(db, identity.user)


@router.post("/switch-tenant", response_model=AuthResponse)
def switch_tenant(
    request_data: SwitchTenantRequest,
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> AuthResponse:
    target_company = db.get(Company, request_data.company_id)
    if not target_company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organisation introuvable",
        )

    if target_company.status != CompanyStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Organisation inactive",
        )

    # Vérification d'autorisation stricte
    if identity.user.is_platform_admin:
        audit = AuditLogEntry(
            actor_user_id=identity.user.id,
            action="super_admin_tenant_switch",
            target_type="company",
            target_id=str(target_company.id),
            company_id=target_company.id,
            safe_metadata={
                "source_tenant": str(identity.user.company_id),
                "target_tenant": str(target_company.id),
                "admin_email": identity.user.email,
            },
        )
        db.add(audit)
    else:
        is_primary = (identity.user.company_id == target_company.id)
        has_membership = False
        if not is_primary:
            has_membership = (
                db.scalar(
                    select(func.count())
                    .select_from(CompanyMembership)
                    .where(
                        CompanyMembership.user_id == identity.user.id,
                        CompanyMembership.company_id == target_company.id,
                        CompanyMembership.is_active == True,
                    )
                )
                or 0
            ) > 0

        if not (is_primary or has_membership):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Accès non autorisé à cette organisation",
            )

    identity.user.company_id = target_company.id
    db.commit()
    db.refresh(identity.user)

    access_token, access_expires_at = create_access_token(
        identity.user.id,
        target_company.id,
        identity.auth_session.id,
    )

    orgs = _get_user_organizations(db, identity.user)
    return AuthResponse(
        access_token=access_token,
        refresh_token=identity.raw_token,
        access_expires_at=access_expires_at,
        refresh_expires_at=identity.auth_session.expires_at,
        user=_user_response(identity.user),
        company=_company_response(target_company),
        organizations=orgs,
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
    return MessageResponse(message="Si le compte existe, un email a été envoyé.")


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
    return MessageResponse(message="Mot de passe modifié. Reconnectez-vous.")
