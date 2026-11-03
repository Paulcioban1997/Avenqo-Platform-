"""Base contracts and data models for advertising connectors (Google Ads & Meta Ads)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
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


def resolve_date_range(period: str) -> tuple[str, str]:
    """Calculates ISO (YYYY-MM-DD) start and end dates based on standard period filters."""
    today = datetime.now(timezone.utc).date()
    p = period.lower().strip()
    if p in ("7d", "last_7d", "last_7_days"):
        start = today - timedelta(days=7)
    elif p in ("90d", "last_90d", "last_quarter", "quarter"):
        start = today - timedelta(days=90)
    else:  # default 30d
        start = today - timedelta(days=30)
    return start.isoformat(), today.isoformat()


@dataclass
class AdCampaign:
    id: str
    name: str
    status: str  # ENABLED, PAUSED, REMOVED, ARCHIVED
    provider: str  # google_ads, meta_ads
    currency: str = "CAD"  # Native currency of the ad account (CAD, USD, EUR, etc.)
    daily_budget_native: Decimal | None = None
    lifetime_budget_native: Decimal | None = None
    spend_native: Decimal = Decimal("0.00")
    impressions: int = 0
    clicks: int = 0
    conversions: int = 0
    ctr: float = 0.0
    cpc_native: Decimal = Decimal("0.00")
    roas: float = 0.0

    # Explicit conversion metadata if exchange rate was applied
    converted_currency: str | None = None
    exchange_rate: Decimal | None = None
    exchange_rate_source: str | None = None
    exchange_rate_date: str | None = None
    daily_budget_converted: Decimal | None = None
    lifetime_budget_converted: Decimal | None = None
    spend_converted: Decimal | None = None
    cpc_converted: Decimal | None = None

    @property
    def spend_cad(self) -> Decimal:
        """Backward-compatible helper returning spend in CAD."""
        if self.converted_currency == "CAD" and self.spend_converted is not None:
            return self.spend_converted
        if self.currency == "CAD":
            return self.spend_native
        return self.spend_native

    @property
    def daily_budget_cad(self) -> Decimal | None:
        """Backward-compatible helper returning daily budget in CAD."""
        if self.converted_currency == "CAD" and self.daily_budget_converted is not None:
            return self.daily_budget_converted
        if self.currency == "CAD":
            return self.daily_budget_native
        return self.daily_budget_native

    @property
    def lifetime_budget_cad(self) -> Decimal | None:
        """Backward-compatible helper returning lifetime budget in CAD."""
        if self.converted_currency == "CAD" and self.lifetime_budget_converted is not None:
            return self.lifetime_budget_converted
        if self.currency == "CAD":
            return self.lifetime_budget_native
        return self.lifetime_budget_native

    @property
    def cpc_cad(self) -> Decimal:
        """Backward-compatible helper returning average CPC in CAD."""
        if self.converted_currency == "CAD" and self.cpc_converted is not None:
            return self.cpc_converted
        if self.currency == "CAD":
            return self.cpc_native
        return self.cpc_native


@dataclass
class AdsPerformanceSummary:
    provider: str
    account_id: str | None = None
    account_name: str | None = None
    native_currency: str = "CAD"
    total_spend_native: Decimal = Decimal("0.00")
    total_impressions: int = 0
    total_clicks: int = 0
    total_conversions: int = 0
    average_ctr: float = 0.0
    average_cpc_native: Decimal = Decimal("0.00")
    average_roas: float = 0.0
    campaigns_count: int = 0
    active_campaigns_count: int = 0
    period: str = "last_30d"
    start_date: str | None = None
    end_date: str | None = None

    # Explicit conversion metadata
    reference_currency: str | None = None
    exchange_rate: Decimal | None = None
    exchange_rate_source: str | None = None
    exchange_rate_date: str | None = None
    total_spend_converted: Decimal | None = None
    average_cpc_converted: Decimal | None = None

    @property
    def total_spend_cad(self) -> Decimal:
        if self.reference_currency == "CAD" and self.total_spend_converted is not None:
            return self.total_spend_converted
        if self.native_currency == "CAD":
            return self.total_spend_native
        return self.total_spend_native

    @property
    def average_cpc_cad(self) -> Decimal:
        if self.reference_currency == "CAD" and self.average_cpc_converted is not None:
            return self.average_cpc_converted
        if self.native_currency == "CAD":
            return self.average_cpc_native
        return self.average_cpc_native


@dataclass
class AdsConnectionStatus:
    provider: str
    connected: bool
    configured: bool
    external_account_id: str | None = None
    account_name: str | None = None
    currency: str = "CAD"
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
    async def verify_access(self, credentials: dict[str, Any], account_id: str | None = None) -> dict[str, Any]:
        """Verifies account access, active status and fetches account currency & metadata."""
        ...

    @abstractmethod
    async def list_campaigns(
        self, credentials: dict[str, Any], account_id: str | None = None, period: str = "last_30d"
    ) -> list[AdCampaign]:
        """Fetches campaigns in read-only mode."""
        ...

    @abstractmethod
    async def get_performance(
        self, credentials: dict[str, Any], account_id: str | None = None, period: str = "last_30d"
    ) -> AdsPerformanceSummary:
        """Fetches aggregated campaign performance in read-only mode."""
        ...
