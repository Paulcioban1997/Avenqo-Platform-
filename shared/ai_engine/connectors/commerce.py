"""Provider-neutral contract for tenant-scoped commerce connectors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping
from uuid import UUID


class ConnectorCategory(StrEnum):
    ECOMMERCE = "ecommerce"
    MARKETPLACE = "marketplace"
    PAYMENTS = "payments"
    MARKETING = "marketing"
    FULFILLMENT = "fulfillment"
    ANALYTICS = "analytics"


class ConnectorImplementationStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    COMING_SOON = "COMING_SOON"


class ConnectorAuthMethod(StrEnum):
    OAUTH2 = "oauth2"
    API_KEY = "api_key"


class ConnectorCapability(StrEnum):
    ORDERS = "orders"
    CUSTOMERS = "customers"
    PRODUCTS = "products"
    INVENTORY = "inventory"
    REFUNDS = "refunds"
    PAYMENTS = "payments"
    DISCOUNTS = "discounts"


class ConnectorCapabilityError(NotImplementedError):
    """Raised when a provider does not implement a requested capability."""


@dataclass(frozen=True, slots=True)
class ConnectorDefinition:
    provider: str
    display_name: str
    category: ConnectorCategory
    implementation_status: ConnectorImplementationStatus
    auth_method: ConnectorAuthMethod
    capabilities: frozenset[ConnectorCapability]
    description_key: str = ""
    icon_key: str = "extension"
    supported_regions: tuple[str, ...] = ("global",)
    configuration_requirements: tuple[str, ...] = ()

    @property
    def enabled(self) -> bool:
        return self.implementation_status == ConnectorImplementationStatus.AVAILABLE


@dataclass(frozen=True, slots=True)
class ConnectorPage:
    records: tuple[Mapping[str, Any], ...]
    next_cursor: str | None = None


@dataclass(frozen=True, slots=True)
class ConnectorSyncContext:
    tenant_id: UUID
    connection_id: UUID
    access_token: str
    external_account_id: str
    cursor: str | None = None
    updated_since: str | None = None


class CommerceConnector(ABC):
    """Backend-only provider adapter used by connection and sync services."""

    definition: ConnectorDefinition

    @abstractmethod
    def authenticate(self, *, tenant_id: UUID, configuration: Mapping[str, str]) -> str:
        """Return the provider authorization URL for a tenant-scoped request."""

    @abstractmethod
    async def handle_oauth_callback(
        self,
        *,
        tenant_id: UUID,
        callback_parameters: Mapping[str, str],
    ) -> Mapping[str, Any]:
        """Validate and exchange a provider callback for backend-only credentials."""

    @abstractmethod
    async def test_connection(self, context: ConnectorSyncContext) -> bool:
        """Verify that stored credentials still grant the expected read access."""

    async def sync_orders(self, context: ConnectorSyncContext) -> ConnectorPage:
        self._unsupported(ConnectorCapability.ORDERS)

    async def sync_customers(self, context: ConnectorSyncContext) -> ConnectorPage:
        self._unsupported(ConnectorCapability.CUSTOMERS)

    async def sync_products(self, context: ConnectorSyncContext) -> ConnectorPage:
        self._unsupported(ConnectorCapability.PRODUCTS)

    async def sync_inventory(self, context: ConnectorSyncContext) -> ConnectorPage:
        self._unsupported(ConnectorCapability.INVENTORY)

    async def sync_refunds(self, context: ConnectorSyncContext) -> ConnectorPage:
        self._unsupported(ConnectorCapability.REFUNDS)

    async def sync_payments(self, context: ConnectorSyncContext) -> ConnectorPage:
        self._unsupported(ConnectorCapability.PAYMENTS)

    async def sync_discounts(self, context: ConnectorSyncContext) -> ConnectorPage:
        self._unsupported(ConnectorCapability.DISCOUNTS)

    async def initial_sync(
        self, context: ConnectorSyncContext
    ) -> Mapping[str, tuple[Mapping[str, Any], ...]]:
        raise NotImplementedError

    async def incremental_sync(
        self, context: ConnectorSyncContext
    ) -> Mapping[str, tuple[Mapping[str, Any], ...]]:
        raise NotImplementedError

    async def register_webhooks(self, context: ConnectorSyncContext) -> None:
        raise NotImplementedError

    async def handle_webhook(
        self,
        *,
        tenant_id: UUID,
        headers: Mapping[str, str],
        body: bytes,
    ) -> Mapping[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def get_sync_status(self, context: ConnectorSyncContext) -> str:
        """Return the provider-specific synchronization status."""

    @abstractmethod
    async def disconnect(self, context: ConnectorSyncContext) -> None:
        """Revoke provider credentials when supported."""

    def _unsupported(self, capability: ConnectorCapability) -> None:
        raise ConnectorCapabilityError(
            f"Provider '{self.definition.provider}' does not support '{capability.value}'"
        )