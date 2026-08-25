"""SchÃ©mas HTTP publics de l'authentification Avenqo."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from backend.app.models.base import UserRole


class RegisterRequest(BaseModel):
    """Informations nÃ©cessaires pour crÃ©er une entreprise et son propriÃ©taire."""

    company_name: str = Field(min_length=2, max_length=255)
    company_email: EmailStr
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    country: str = Field(min_length=2, max_length=100)
    timezone: str = Field(default="America/Toronto", min_length=3, max_length=100)
    industry: str = Field(min_length=2, max_length=120)
    website: str | None = Field(default=None, max_length=255)
    region: str = Field(default="North America", min_length=2, max_length=100)
    company_size: str = Field(default="1-10", min_length=1, max_length=50)
    preferred_language: str = Field(default="fr", min_length=2, max_length=10)
    billing_email: EmailStr | None = None
    job_title: str = Field(default="Owner", min_length=1, max_length=120)
    phone: str | None = Field(default=None, max_length=32)
    plan_code: str = Field(default="demo", pattern="^(demo|professional|enterprise)$")
    business_goals: list[str] = Field(default_factory=list, max_length=20)
    current_tools: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("website", mode="before")
    @classmethod
    def normalize_website(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        candidate = value.strip()
        if not candidate.startswith(("http://", "https://")):
            candidate = f"https://{candidate}"
        from pydantic import AnyHttpUrl, TypeAdapter

        return str(TypeAdapter(AnyHttpUrl).validate_python(candidate))

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        """Impose une base simple sans politique impossible Ã  expliquer."""

        requirements = (
            any(character.islower() for character in value),
            any(character.isupper() for character in value),
            any(character.isdigit() for character in value),
            any(not character.isalnum() for character in value),
        )
        if not all(requirements):
            raise ValueError(
                "Le mot de passe doit contenir une minuscule, une majuscule, "
                "un chiffre et un caractÃ¨re spÃ©cial"
            )
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenRequest(BaseModel):
    token: str = Field(min_length=32, max_length=512)


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=32, max_length=512)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(TokenRequest):
    new_password: str = Field(min_length=10, max_length=128)

    _validate_new_password = field_validator("new_password")(
        RegisterRequest.validate_password.__func__
    )


class CompanyResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    subscription_plan: str
    onboarding_status: str
    billing_email: str

    model_config = {"from_attributes": True}


class UserResponse(BaseModel):
    id: UUID
    company_id: UUID
    first_name: str
    last_name: str
    email: EmailStr
    role: UserRole
    permissions: tuple[str, ...]
    is_active: bool
    is_platform_admin: bool = False
    email_verified_at: datetime | None


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    access_expires_at: datetime
    refresh_expires_at: datetime
    user: UserResponse
    company: CompanyResponse


class CurrentAccountResponse(BaseModel):
    user: UserResponse
    company: CompanyResponse


class MessageResponse(BaseModel):
    message: str
    # Frontend must not claim an email was sent when SMTP isn't configured
    # (LoggingAccountNotifier only logs locally, never delivers).
    email_delivery_configured: bool = False
