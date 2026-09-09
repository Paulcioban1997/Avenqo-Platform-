"""HTTP schemas for the tenant commerce connector hub."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, SecretStr


class ConnectorCatalogResponse(BaseModel):
    provider: str
    display_name: str
    category: str
    customer_status: str
    auth_method: str
    capabilities: list[str]
    description_key: str
    icon_key: str
    supported_regions: list[str]
    configuration_requirements: list[str]
    configured: bool
    internal_test_available: bool
    documentation_url: str
    supports_oauth: bool
    supports_webhooks: bool
    supports_incremental_sync: bool
    external_registration_required: bool
    callback_urls_required: bool
    webhook_urls_required: bool
    scopes_required: list[str]
    review_required: bool
    sandbox_available: bool
    markets_supported: list[str]
    priority: str


class ShopifyAuthorizationRequest(BaseModel):
    shop_domain: str = Field(min_length=1, max_length=255)


class ShopifyAuthorizationResponse(BaseModel):
    authorization_url: str
    expires_at: datetime


class WooCommerceAuthorizationRequest(BaseModel):
    store_url: str = Field(min_length=1, max_length=2048)


class WooCommerceManualConnectionRequest(WooCommerceAuthorizationRequest):
    consumer_key: SecretStr
    consumer_secret: SecretStr


class WooCommerceCallbackPayload(BaseModel):
    key_id: int | None = None
    user_id: str = Field(min_length=1, max_length=255)
    consumer_key: SecretStr
    consumer_secret: SecretStr
    key_permissions: str = Field(min_length=1, max_length=32)


class CommerceConnectionResponse(BaseModel):
    id: UUID
    provider: str
    external_account_id: str
    display_name: str | None
    status: str
    connection_status: str
    sync_status: str
    capabilities: list[str]
    records_processed: int
    current_entity: str | None
    error_category: str | None
    last_successful_sync: datetime | None
    sync_started_at: datetime | None
    dataset_id: UUID | None
    reauthorization_available: bool = False


class CommerceSyncAcceptedResponse(BaseModel):
    connection_id: UUID
    status: str


class CommerceWebhookResponse(BaseModel):
    accepted: bool
    duplicate: bool