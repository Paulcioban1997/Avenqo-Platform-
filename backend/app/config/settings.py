from __future__ import annotations

from functools import lru_cache
from typing import Annotated, List

from pydantic import Field
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Centralise les paramÃ¨tres chargÃ©s depuis les variables d'environnement."""

    model_config = SettingsConfigDict(
        env_file="backend/.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="Avenqo", alias="APP_NAME")
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
    cors_origins: Annotated[List[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"],
        alias="CORS_ORIGINS",
    )
    # Hôtes HTTP autorisés (TrustedHostMiddleware). "*" en développement ; à
    # restreindre explicitement (ex. api.avenqo.ca) en production.
    allowed_hosts: Annotated[List[str], NoDecode] = Field(
        default_factory=lambda: ["*"],
        alias="ALLOWED_HOSTS",
    )
    database_url: str = Field(
        default="sqlite:///./var/avenqo.db",
        validation_alias="DATABASE_URL",
    )
    artifact_root: str = Field(default="var/artifacts", alias="ARTIFACT_ROOT")
    model_registry_root: str = Field(default="var/models", alias="MODEL_REGISTRY_ROOT")
    dataset_max_upload_mb: int = Field(default=50, alias="DATASET_MAX_UPLOAD_MB")
    llm_provider: str = Field(default="openai", alias="LLM_PROVIDER")
    llm_model: str = Field(default="gpt-4o-mini", alias="LLM_MODEL")
    # Chaque fournisseur IA a son propre espace de noms de modèles (les modèles
    # OpenAI ne sont pas valides pour Anthropic ou Gemini, et inversement) —
    # `llm_model` reste le défaut/rétrocompatible pour le fournisseur unique
    # (Phase 28), mais le Resilient AI Gateway (Phase 32) utilise ces valeurs
    # spécifiques par fournisseur pour éviter les erreurs "modèle inconnu".
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    anthropic_model: str = Field(default="claude-3-5-sonnet-20241022", alias="ANTHROPIC_MODEL")
    gemini_model: str = Field(default="gemini-flash-latest", alias="GEMINI_MODEL")
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
    frontend_url: str = Field(default="http://localhost:8080", alias="FRONTEND_URL")
    smtp_host: str | None = Field(default=None, alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_username: str | None = Field(default=None, alias="SMTP_USERNAME")
    smtp_password: str | None = Field(default=None, alias="SMTP_PASSWORD")
    smtp_from_email: str = Field(default="noreply@avenqo.ca", alias="SMTP_FROM_EMAIL")
    smtp_use_tls: bool = Field(default=True, alias="SMTP_USE_TLS")
    avenqo_owner_notification_email: str | None = Field(default=None, alias="AVENQO_OWNER_NOTIFICATION_EMAIL")
    stripe_secret_key: str | None = Field(default=None, alias="STRIPE_SECRET_KEY")
    stripe_webhook_secret: str | None = Field(default=None, alias="STRIPE_WEBHOOK_SECRET")
    stripe_price_demo: str | None = Field(default=None, alias="STRIPE_PRICE_DEMO")
    stripe_price_professional: str | None = Field(default=None, alias="STRIPE_PRICE_PROFESSIONAL")
    stripe_price_enterprise: str | None = Field(default=None, alias="STRIPE_PRICE_ENTERPRISE")
    ai_max_tool_iterations: int = Field(default=5, ge=1, le=20, alias="AI_MAX_TOOL_ITERATIONS")
    ai_max_tools_per_request: int = Field(default=8, ge=1, le=50, alias="AI_MAX_TOOLS_PER_REQUEST")
    ai_max_tool_result_chars: int = Field(default=8000, ge=500, alias="AI_MAX_TOOL_RESULT_CHARS")
    # Quotas d'usage IA configurables par plan Avenqo (demo/professional/enterprise/
    # custom_enterprise). Format : {"<plan_code>": {"<metric>": <int>}}. Aucune valeur
    # commerciale n'est définie par défaut ({} = aucune limite tant que non configurée) :
    # voir backend/app/ai/usage/policy.py pour les noms de métriques reconnus.
    ai_quota_limits: dict[str, dict[str, int]] = Field(default_factory=dict, alias="AI_QUOTA_LIMITS")
    # Politique de fraîcheur des modèles/prédictions (Phase 31.1) : défaut TECHNIQUE
    # configurable (pas un engagement commercial) — voir backend/app/services/prediction_freshness.py.
    ai_freshness_stale_after_days: int = Field(default=7, ge=0, alias="AI_FRESHNESS_STALE_AFTER_DAYS")
    ai_freshness_expired_after_days: int = Field(default=30, ge=0, alias="AI_FRESHNESS_EXPIRED_AFTER_DAYS")
    ai_freshness_block_on_expired: bool = Field(default=True, alias="AI_FRESHNESS_BLOCK_ON_EXPIRED")
    # Resilient AI Gateway (Phase 32) : ordre de fournisseurs primaire/fallback
    # (aucun engagement commercial — défauts techniques). Un fallback sans clé
    # API configurée est simplement ignoré par `LLMProviderFactory.create_gateway`.
    ai_primary_provider: str = Field(default="openai", alias="AI_PRIMARY_PROVIDER")
    ai_fallback_provider_1: str | None = Field(default=None, alias="AI_FALLBACK_PROVIDER_1")
    ai_fallback_provider_2: str | None = Field(default=None, alias="AI_FALLBACK_PROVIDER_2")
    ai_gateway_max_retries: int = Field(default=2, ge=0, le=10, alias="AI_GATEWAY_MAX_RETRIES")
    ai_gateway_base_delay_seconds: float = Field(default=0.5, ge=0.0, le=30.0, alias="AI_GATEWAY_BASE_DELAY_SECONDS")
    ai_gateway_max_delay_seconds: float = Field(default=4.0, ge=0.0, le=60.0, alias="AI_GATEWAY_MAX_DELAY_SECONDS")
    ai_gateway_circuit_failure_threshold: int = Field(default=3, ge=1, le=20, alias="AI_GATEWAY_CIRCUIT_FAILURE_THRESHOLD")
    ai_gateway_circuit_cooldown_seconds: float = Field(default=30.0, ge=1.0, le=600.0, alias="AI_GATEWAY_CIRCUIT_COOLDOWN_SECONDS")
    # Avenqo Platform Support AI (Phase 32) : dossier de la base de connaissances
    # produit (jamais les données métier d'un tenant — voir backend/app/ai/support/).
    ai_support_knowledge_root: str = Field(default="platform_knowledge", alias="AI_SUPPORT_KNOWLEDGE_ROOT")
    # Rate limiting (Phase 34) : limites TECHNIQUES par défaut (pas un engagement
    # commercial), configurables par déploiement. Fenêtre glissante en mémoire —
    # voir backend/app/core/rate_limit.py (limitation : par process, non partagée
    # entre plusieurs workers/instances ; acceptable pour ce stade du produit).
    rate_limit_enabled: bool = Field(default=True, alias="RATE_LIMIT_ENABLED")
    rate_limit_auth_per_minute: int = Field(default=10, ge=1, alias="RATE_LIMIT_AUTH_PER_MINUTE")
    rate_limit_ai_per_minute: int = Field(default=30, ge=1, alias="RATE_LIMIT_AI_PER_MINUTE")
    rate_limit_billing_per_minute: int = Field(default=20, ge=1, alias="RATE_LIMIT_BILLING_PER_MINUTE")
    rate_limit_admin_per_minute: int = Field(default=60, ge=1, alias="RATE_LIMIT_ADMIN_PER_MINUTE")
    rate_limit_default_per_minute: int = Field(default=120, ge=1, alias="RATE_LIMIT_DEFAULT_PER_MINUTE")

    # Sauvegarde/restauration (remédiation post-Phase 34) : répertoire local de
    # stockage des archives et politique de rétention par défaut (technique,
    # pas un engagement commercial) — voir backend/app/services/backup_service.py
    # et docs/backup-and-disaster-recovery.md.
    backup_root: str = Field(default="var/backups", alias="BACKUP_ROOT")
    backup_retention_days: int = Field(default=30, ge=1, alias="BACKUP_RETENTION_DAYS")
    # Stockage S3-compatible (Railway Storage Bucket / MinIO / AWS S3) — optionnel.
    # Si non configuré, les backups restent sur le disque local (comportement actuel).
    backup_s3_endpoint_url: str | None = Field(default=None, alias="BACKUP_S3_ENDPOINT_URL")
    backup_s3_bucket: str | None = Field(default=None, alias="BACKUP_S3_BUCKET")
    backup_s3_access_key: str | None = Field(default=None, alias="BACKUP_S3_ACCESS_KEY")
    backup_s3_secret_key: str | None = Field(default=None, alias="BACKUP_S3_SECRET_KEY")
    backup_s3_region: str = Field(default="auto", alias="BACKUP_S3_REGION")

    # Bootstrap sécurisé du compte platform_admin propriétaire (scripts/bootstrap_platform_admin.py).
    # Jamais loggé ni exposé via une réponse API. Voir docs/platform-admin-setup.md.
    platform_admin_email: str | None = Field(default=None, alias="PLATFORM_ADMIN_EMAIL")
    platform_admin_password: str | None = Field(default=None, alias="PLATFORM_ADMIN_PASSWORD")

    @field_validator("cors_origins", "allowed_hosts", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        """Accepte une liste JSON ou une chaîne séparée par des virgules (`.env`)."""

        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                return value
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return value

    @field_validator(
        "smtp_host", "smtp_username", "smtp_password",
        "stripe_secret_key", "stripe_webhook_secret",
        "stripe_price_demo", "stripe_price_professional", "stripe_price_enterprise",
        mode="before",
    )
    @classmethod
    def blank_to_none(cls, value: object) -> object:
        """Une valeur vide (ex. `SMTP_HOST=` dans un .env) compte comme absente."""

        if isinstance(value, str) and not value.strip():
            return None
        return value

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
            missing: list[str] = []
            if not self.database_url.strip() or self.database_url == "sqlite:///./var/avenqo.db":
                missing.append("DATABASE_URL")
            if self.auth_jwt_secret == "development-only-change-this-jwt-secret":
                missing.append("AUTH_JWT_SECRET")
            for name, value in (
                ("STRIPE_SECRET_KEY", self.stripe_secret_key),
                ("STRIPE_WEBHOOK_SECRET", self.stripe_webhook_secret),
                ("STRIPE_PRICE_DEMO", self.stripe_price_demo),
                ("STRIPE_PRICE_PROFESSIONAL", self.stripe_price_professional),
            ):
                if not value:
                    missing.append(name)
            if not self.frontend_url.startswith("https://"):
                missing.append("FRONTEND_URL")
            if not self.cors_origins or any(
                not origin.startswith("https://") for origin in self.cors_origins
            ):
                missing.append("CORS_ORIGINS")
            if not self.allowed_hosts or "*" in self.allowed_hosts:
                missing.append("ALLOWED_HOSTS")
            if missing:
                raise ValueError(
                    "Configuration production manquante ou non sécurisée : "
                    + ", ".join(missing)
                )
            # SMTP volontairement NON bloquant au dÃ©marrage : l'app doit pouvoir
            # dÃ©marrer sans serveur email. Sans SMTP_HOST, `get_account_notifier`
            # retombe sur LoggingAccountNotifier et les rÃ©ponses signalent
            # `email_delivery_configured=false` (erreur claire, jamais un crash).
        return self

    @property
    def billing_enabled(self) -> bool:
        """Facturation self-service Demo/Professional pleinement configurée."""

        return bool(
            self.stripe_secret_key
            and self.stripe_webhook_secret
            and self.stripe_price_demo
            and self.stripe_price_professional
        )

    @property
    def backup_s3_enabled(self) -> bool:
        """Stockage S3 de backup configuré (bucket + clés requis ; endpoint optionnel)."""

        return bool(
            self.backup_s3_bucket
            and self.backup_s3_access_key
            and self.backup_s3_secret_key
        )

    @property
    def app_title(self) -> str:
        return self.app_name

    def stripe_price_id(self, plan_code: str) -> str | None:
        return {
            "demo": self.stripe_price_demo,
            "professional": self.stripe_price_professional,
        }.get(plan_code)

    def stripe_plan_code(self, price_id: str) -> str | None:
        prices = {
            self.stripe_price_demo: "demo",
            self.stripe_price_professional: "professional",
        }
        return prices.get(price_id)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

