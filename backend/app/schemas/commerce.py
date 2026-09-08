"""HTTP schemas for the tenant commerce connector hub."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ConnectorCatalogResponse(BaseModel):
    provider: str
    display_name: str
    category: str
    implementation_status: str
    auth_method: str
    capabilities: list[str]
    description_key: str
    icon_key: str
    supported_regions: list[str]
    configuration_requirements: list[str]
    configured: bool


class ShopifyAuthorizationRequest(BaseModel):
    shop_domain: str = Field(min_length=1, max_length=255)


class ShopifyAuthorizationResponse(BaseModel):
    authorization_url: str
    expires_at: datetime


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


class CommerceSyncAcceptedResponse(BaseModel):
    connection_id: UUID
    status: str


class CommerceWebhookResponse(BaseModel):
    accepted: bool
    duplicate: bool