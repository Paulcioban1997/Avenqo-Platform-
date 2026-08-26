"""Cas d'usage d'authentification et d'inscription multi-tenant."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
import re
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.config.settings import get_settings
from backend.app.core.security import (
    create_access_token,
    decode_access_token,
    generate_token,
    hash_password,
    hash_token,
    verify_password,
)
from backend.app.models import (
    AccountToken,
    AccountTokenPurpose,
    AuthSession,
    Company,
    CompanyOnboarding,
    CompanyStatus,
    OnboardingStatus,
    User,
    UserRole,
)
from backend.app.schemas.auth import RegisterRequest
from backend.app.services.account_notifications import AccountNotifier

logger = logging.getLogger(__name__)


class AuthenticationError(ValueError):
    """Erreur volontairement générique pour ne pas révéler les comptes."""


class ConflictError(ValueError):
    """Une ressource unique existe déjà."""


@dataclass(frozen=True, slots=True)
class AuthResult:
    access_token: str
    refresh_token: str
    access_expires_at: datetime
    refresh_expires_at: datetime
    user: User


class AuthService:
    """Crée les tenants, employés, sessions et jetons temporaires."""

    def __init__(self, session: Session, notifier: AccountNotifier) -> None:
        self._session = session
        self._notifier = notifier

    def register(self, request: RegisterRequest) -> tuple[Company, User, bool]:
        email = str(request.email).strip().lower()
        company_email = str(request.company_email).strip().lower()
        if self._session.scalar(select(User).where(User.email == email)):
            raise ConflictError("Un compte utilise déjà cet email")
        if self._session.scalar(select(Company).where(Company.email == company_email)):
            raise ConflictError("Une entreprise utilise déjà cet email")

        from backend.app.core.locale_catalog import currency_for_country

        company = Company(
            name=request.company_name.strip(),
            slug=self._unique_slug(request.company_name),
            email=company_email,
            billing_email=str(request.billing_email or request.company_email).strip().lower(),
            country=request.country.strip(),
            timezone=request.timezone.strip(),
            industry=request.industry.strip(),
            website=request.website.strip() if request.website else None,
            region=request.region.strip(),
            company_size=request.company_size.strip(),
            preferred_language=request.preferred_language.strip(),
            # Devise : valeur explicite si fournie, sinon default du PAYS (jamais
            # déduit de la langue), fallback technique USD si pays inconnu.
            currency_code=(request.currency_code or "").strip().upper()
            or currency_for_country(request.country),
            subscription_plan=request.plan_code,
            status=CompanyStatus.ACTIVE,
        )
        user = User(
            company=company,
            first_name=request.first_name.strip(),
            last_name=request.last_name.strip(),
            job_title=request.job_title.strip(),
            phone=request.phone.strip() if request.phone else None,
            email=email,
            password_hash=hash_password(request.password),
            role=UserRole.OWNER,
            is_active=True,
        )
        self._session.add_all((company, user))
        self._session.flush()
        if request.business_goals or request.current_tools:
            self._session.add(
                CompanyOnboarding(
                    company_id=company.id,
                    status=OnboardingStatus.PENDING,
                    business_goals=request.business_goals,
                    current_tools=request.current_tools,
                    team_size=request.company_size,
                    refined_industry=request.industry.strip(),
                )
            )
            self._session.flush()
        token = self._create_account_token(user, AccountTokenPurpose.EMAIL_VERIFICATION, 24)
        self._session.commit()
        verification_email_sent = False
        try:
            self._notifier.send_email_verification(user.email, token)
            verification_email_sent = True
        except Exception:
            # SMTP is an external side effect; never undo a committed account.
            logger.exception("Verification email delivery failed for %s", user.email)
        try:
            notify = getattr(self._notifier, "send_new_company", None)
            if notify:
                notify(company, user, request)
        except Exception:
            # Account creation remains successful when owner SMTP is unavailable.
            logger.exception("Owner notification failed for company %s", company.id)
        return company, user, verification_email_sent

    def login(self, email: str, password: str) -> AuthResult:
        user = self._session.scalar(select(User).where(User.email == email.strip().lower()))
        if user is None or not user.is_active or not verify_password(password, user.password_hash):
            raise AuthenticationError("Email ou mot de passe incorrect")
        if user.email_verified_at is None:
            raise AuthenticationError("L'adresse email doit être vérifiée")

        now = datetime.now(timezone.utc)
        refresh_token = generate_token()
        refresh_expires_at = now + timedelta(days=get_settings().auth_refresh_days)
        auth_session = AuthSession(
            id=uuid4(),
            user=user,
            token_hash=hash_token(refresh_token),
            created_at=now,
            expires_at=refresh_expires_at,
        )
        self._session.add(auth_session)
        user.last_login = now
        self._session.commit()
        access_token, access_expires_at = create_access_token(
            user.id,
            user.company_id,
            auth_session.id,
        )
        return AuthResult(
            access_token=access_token,
            refresh_token=refresh_token,
            access_expires_at=access_expires_at,
            refresh_expires_at=refresh_expires_at,
            user=user,
        )

    def authenticate(self, access_token: str) -> tuple[AuthSession, User]:
        try:
            claims = decode_access_token(access_token)
            session_id = UUID(str(claims["session_id"]))
            user_id = UUID(str(claims["sub"]))
            company_id = UUID(str(claims["tenant_id"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise AuthenticationError("Session invalide ou expirée") from exc
        auth_session = self._session.get(AuthSession, session_id)
        now = datetime.now(timezone.utc)
        if (
            auth_session is None
            or auth_session.revoked_at is not None
            or self._aware(auth_session.expires_at) <= now
            or not auth_session.user.is_active
            or auth_session.user.id != user_id
            or auth_session.user.company_id != company_id
        ):
            raise AuthenticationError("Session invalide ou expirée")
        return auth_session, auth_session.user

    def refresh(self, refresh_token: str) -> AuthResult:
        auth_session = self._session.scalar(select(AuthSession).where(
            AuthSession.token_hash == hash_token(refresh_token),
        ))
        now = datetime.now(timezone.utc)
        if (
            auth_session is None
            or auth_session.revoked_at is not None
            or self._aware(auth_session.expires_at) <= now
            or not auth_session.user.is_active
        ):
            raise AuthenticationError("Refresh token invalide ou expiré")

        rotated_refresh_token = generate_token()
        auth_session.token_hash = hash_token(rotated_refresh_token)
        access_token, access_expires_at = create_access_token(
            auth_session.user.id,
            auth_session.user.company_id,
            auth_session.id,
        )
        self._session.commit()
        return AuthResult(
            access_token=access_token,
            refresh_token=rotated_refresh_token,
            access_expires_at=access_expires_at,
            refresh_expires_at=self._aware(auth_session.expires_at),
            user=auth_session.user,
        )

    def logout(self, access_token: str) -> None:
        auth_session, _ = self.authenticate(access_token)
        auth_session.revoked_at = datetime.now(timezone.utc)
        self._session.commit()

    def verify_email(self, raw_token: str) -> User:
        token = self._consume_account_token(raw_token, AccountTokenPurpose.EMAIL_VERIFICATION)
        token.user.email_verified_at = datetime.now(timezone.utc)
        self._session.commit()
        return token.user

    def resend_verification(self, email: str) -> None:
        user = self._session.scalar(select(User).where(User.email == email.strip().lower()))
        if user is None or user.email_verified_at is not None:
            return
        token = self._create_account_token(user, AccountTokenPurpose.EMAIL_VERIFICATION, 24)
        self._session.commit()
        self._notifier.send_email_verification(user.email, token)

    def forgot_password(self, email: str) -> None:
        user = self._session.scalar(select(User).where(User.email == email.strip().lower()))
        if user is None or not user.is_active:
            return
        token = self._create_account_token(user, AccountTokenPurpose.PASSWORD_RESET, 1)
        self._session.commit()
        self._notifier.send_password_reset(user.email, token)

    def reset_password(self, raw_token: str, new_password: str) -> None:
        token = self._consume_account_token(raw_token, AccountTokenPurpose.PASSWORD_RESET)
        token.user.password_hash = hash_password(new_password)
        now = datetime.now(timezone.utc)
        for auth_session in token.user.auth_sessions:
            if auth_session.revoked_at is None:
                auth_session.revoked_at = now
        self._session.commit()

    def _create_account_token(self, user: User, purpose: AccountTokenPurpose, hours: int) -> str:
        now = datetime.now(timezone.utc)
        for existing in user.account_tokens:
            if existing.purpose == purpose and existing.used_at is None:
                existing.used_at = now
        raw_token = generate_token()
        self._session.add(AccountToken(
            user=user,
            purpose=purpose,
            token_hash=hash_token(raw_token),
            created_at=now,
            expires_at=now + timedelta(hours=hours),
        ))
        return raw_token

    def _consume_account_token(self, raw_token: str, purpose: AccountTokenPurpose) -> AccountToken:
        token = self._session.scalar(select(AccountToken).where(
            AccountToken.token_hash == hash_token(raw_token),
            AccountToken.purpose == purpose,
        ))
        if token is None or token.used_at is not None or self._aware(token.expires_at) <= datetime.now(timezone.utc):
            raise AuthenticationError("Jeton invalide ou expiré")
        token.used_at = datetime.now(timezone.utc)
        return token

    def _unique_slug(self, company_name: str) -> str:
        base = re.sub(r"[^a-z0-9]+", "-", company_name.lower()).strip("-") or "company"
        candidate = base
        suffix = 2
        while self._session.scalar(select(Company).where(Company.slug == candidate)):
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)