from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralise les paramÃ¨tres chargÃ©s depuis les variables d'environnement."""

    model_config = SettingsConfigDict(
        env_file="backend/.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="PMC Solutions AI Platform", alias="APP_NAME")
    app_version: str = Field(default="0.1.0", alias="APP_VERSION")
    app_description: str = Field(
        default="Enterprise-grade SaaS AI Platform foundation",
        alias="APP_DESCRIPTION",
    )
    environment: str = Field(default="development", alias="ENVIRONMENT")
    debug: bool = Field(default=True, alias="DEBUG")
    api_v1_prefix: str = Field(default="/api/v1", alias="API_V1_PREFIX")
    host: str = Field(default="127.0.0.1", alias="HOST")
    port: int = Field(default=8000, alias="PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    cors_origins: List[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"],
        alias="CORS_ORIGINS",
    )
    database_url: str = Field(
        default="sqlite:///./var/avenqo.db",
        alias="DATABASE_URL",
    )
    artifact_root: str = Field(default="var/artifacts", alias="ARTIFACT_ROOT")
    model_registry_root: str = Field(default="var/models", alias="MODEL_REGISTRY_ROOT")
    dataset_max_upload_mb: int = Field(default=50, alias="DATASET_MAX_UPLOAD_MB")
    llm_provider: str = Field(default="openai", alias="LLM_PROVIDER")
    llm_model: str = Field(default="gpt-4o-mini", alias="LLM_MODEL")
    llm_temperature: float = Field(default=0.2, ge=0.0, le=1.0, alias="LLM_TEMPERATURE")
    llm_max_tokens: int = Field(default=800, ge=1, le=8192, alias="LLM_MAX_TOKENS")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    google_ai_api_key: str | None = Field(default=None, alias="GOOGLE_AI_API_KEY")
    auth_access_minutes: int = Field(default=15, alias="AUTH_ACCESS_MINUTES")
    auth_refresh_days: int = Field(default=30, alias="AUTH_REFRESH_DAYS")
    auth_jwt_secret: str = Field(
        default="development-only-change-this-jwt-secret",
        min_length=32,
        alias="AUTH_JWT_SECRET",
    )
    auth_jwt_algorithm: str = Field(default="HS256", alias="AUTH_JWT_ALGORITHM")
    auth_jwt_issuer: str = Field(default="avenqo-api", alias="AUTH_JWT_ISSUER")
    auth_jwt_audience: str = Field(default="avenqo-clients", alias="AUTH_JWT_AUDIENCE")
    frontend_url: str = Field(default="http://localhost:3000", alias="FRONTEND_URL")
    smtp_host: str | None = Field(default=None, alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_username: str | None = Field(default=None, alias="SMTP_USERNAME")
    smtp_password: str | None = Field(default=None, alias="SMTP_PASSWORD")
    smtp_from_email: str = Field(default="noreply@avenqo.ca", alias="SMTP_FROM_EMAIL")
    smtp_use_tls: bool = Field(default=True, alias="SMTP_USE_TLS")
    stripe_secret_key: str | None = Field(default=None, alias="STRIPE_SECRET_KEY")
    stripe_webhook_secret: str | None = Field(default=None, alias="STRIPE_WEBHOOK_SECRET")
    stripe_price_starter: str | None = Field(default=None, alias="STRIPE_PRICE_STARTER")
    stripe_price_professional: str | None = Field(default=None, alias="STRIPE_PRICE_PROFESSIONAL")
    stripe_price_enterprise: str | None = Field(default=None, alias="STRIPE_PRICE_ENTERPRISE")
    ai_max_tool_iterations: int = Field(default=5, ge=1, le=20, alias="AI_MAX_TOOL_ITERATIONS")
    ai_max_tools_per_request: int = Field(default=8, ge=1, le=50, alias="AI_MAX_TOOLS_PER_REQUEST")
    ai_max_tool_result_chars: int = Field(default=8000, ge=500, alias="AI_MAX_TOOL_RESULT_CHARS")

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug(cls, value: object) -> object:
        """Accepte aussi les noms d'environnement courants."""

        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "production", "prod"}:
                return False
            if normalized in {"development", "dev"}:
                return True
        return value

    @model_validator(mode="after")
    def validate_production_auth(self) -> "Settings":
        if self.environment.lower() in {"production", "prod"}:
            if self.auth_jwt_secret == "development-only-change-this-jwt-secret":
                raise ValueError("AUTH_JWT_SECRET doit Ãªtre remplacÃ© en production")
            if not self.smtp_host:
                raise ValueError("SMTP_HOST est requis en production")
            stripe_values = (
                self.stripe_secret_key,
                self.stripe_webhook_secret,
                self.stripe_price_starter,
                self.stripe_price_professional,
                self.stripe_price_enterprise,
            )
            if not all(stripe_values):
                raise ValueError("La configuration Stripe complÃ¨te est requise en production")
        return self

    @property
    def app_title(self) -> str:
        return self.app_name

    def stripe_price_id(self, plan_code: str) -> str | None:
        return {
            "starter": self.stripe_price_starter,
            "professional": self.stripe_price_professional,
            "enterprise": self.stripe_price_enterprise,
        }.get(plan_code)

    def stripe_plan_code(self, price_id: str) -> str | None:
        prices = {
            self.stripe_price_starter: "starter",
            self.stripe_price_professional: "professional",
            self.stripe_price_enterprise: "enterprise",
        }
        return prices.get(price_id)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

