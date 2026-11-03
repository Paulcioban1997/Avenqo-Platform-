"""Base contracts and data models for advertising connectors (Google Ads & Meta Ads)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID


class AdsConnectorError(Exception):
    """Raised when an advertising connector encounters an error."""
    def __init__(self, message: str, code: str = "ADS_CONNECTOR_ERROR", status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class AdsConfigurationMissingError(AdsConnectorError):
    """Raised when provider developer token, client ID, or app credentials are not configured."""
    def __init__(self, provider: str, details: str = "") -> None:
        super().__init__(
            f"Configuration {provider} manquante ou incomplète. {details}".strip(),
            code="ADS_CONFIGURATION_MISSING",
            status_code=503,
        )
        self.provider = provider


@dataclass
class AdCampaign:
    id: str
    name: str
    status: str  # ENABLED, PAUSED, REMOVED, ARCHIVED
    provider: str  # google_ads, meta_ads
    daily_budget_cad: Decimal | None = None
    lifetime_budget_cad: Decimal | None = None
    spend_cad: Decimal = Decimal("0.00")
    impressions: int = 0
    clicks: int = 0
    conversions: int = 0
    ctr: float = 0.0
    cpc_cad: Decimal = Decimal("0.00")
    roas: float = 0.0


@dataclass
class AdsPerformanceSummary:
    provider: str
    currency: str = "CAD"
    total_spend_cad: Decimal = Decimal("0.00")
    total_impressions: int = 0
    total_clicks: int = 0
    total_conversions: int = 0
    average_ctr: float = 0.0
    average_cpc_cad: Decimal = Decimal("0.00")
    average_roas: float = 0.0
    campaigns_count: int = 0
    active_campaigns_count: int = 0
    period: str = "last_30d"


@dataclass
class AdsConnectionStatus:
    provider: str
    connected: bool
    configured: bool
    external_account_id: str | None = None
    account_name: str | None = None
    status: str = "DISCONNECTED"
    granted_scopes: list[str] = field(default_factory=list)
    last_successful_sync: datetime | None = None
    error_message: str | None = None
    setup_instructions: str | None = None


class BaseAdsConnector(ABC):
    """Abstract interface that all ad platform connectors must satisfy."""

    @abstractmethod
    def get_auth_url(self, company_id: UUID, user_id: UUID, state: str) -> str:
        """Constructs the provider OAuth authorization URL."""
        ...

    @abstractmethod
    async def exchange_code(self, code: str, redirect_uri: str | None = None) -> dict[str, Any]:
        """Exchanges authorization code for credentials/tokens."""
        ...

    @abstractmethod
    async def refresh_token(self, credentials: dict[str, Any]) -> dict[str, Any]:
        """Refreshes an expiring access token."""
        ...

    @abstractmethod
    async def list_campaigns(self, credentials: dict[str, Any], account_id: str | None = None) -> list[AdCampaign]:
        """Fetches campaigns in read-only mode."""
        ...

    @abstractmethod
    async def get_performance(
        self, credentials: dict[str, Any], account_id: str | None = None, period: str = "last_30d"
    ) -> AdsPerformanceSummary:
        """Fetches aggregated campaign performance in read-only mode."""
        ...

