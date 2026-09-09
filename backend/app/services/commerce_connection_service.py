"""Tenant-safe lifecycle for commerce provider connections."""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.connectors.shopify import ShopifyConnector, ShopifyConnectorError
from backend.app.connectors.woocommerce import (
    WooCommerceAuthenticationError,
    WooCommerceConnector,
    WooCommerceConnectorError,
    WooCommercePermissionError,
)
from backend.app.core.security import hash_token
from backend.app.models import (
    CommerceConnection,
    CommerceConnectionStatus,
    CommerceOAuthState,
)
from backend.app.services.audit_log_service import AuditLogService
from backend.app.services.connector_secret_cipher import ConnectorSecretCipher
from shared.ai_engine.connectors.commerce import ConnectorSyncContext
from shared.ai_engine.connectors.registry import CommerceConnectorRegistry
from shared.ai_engine.contracts import TenantContext

logger = logging.getLogger(__name__)


class CommerceConnectionError(RuntimeError):
    pass


class CommerceConnectionNotFound(CommerceConnectionError):
    pass


class CommerceAuthorizationError(CommerceConnectionError):
    pass


@dataclass(frozen=True, slots=True)
class CommerceAuthorizationStart:
    authorization_url: str
    state: str
    expires_at: datetime


class CommerceConnectionService:
    _STATE_TTL = timedelta(minutes=10)
    _WOOCOMMERCE_STATE_TTL = timedelta(minutes=30)
    _REFRESH_MARGIN = timedelta(minutes=2)

    def __init__(
        self,
        db: Session,
        registry: CommerceConnectorRegistry,
        cipher: ConnectorSecretCipher,
        audit: AuditLogService | None = None,
    ) -> None:
        self._db = db
        self._registry = registry
        self._cipher = cipher
        self._audit = audit or AuditLogService(db)

    def begin_shopify_oauth(
        self,
        tenant: TenantContext,
        *,
        actor_user_id: UUID,
        shop_domain: str,
    ) -> CommerceAuthorizationStart:
        connector = self._shopify()
        shop = connector.normalize_shop_domain(shop_domain)
        raw_state = secrets.token_urlsafe(48)
        expires_at = self._now() + self._STATE_TTL
        oauth_state = CommerceOAuthState(
            company_id=tenant.company_id,
            actor_user_id=actor_user_id,
            provider="shopify",
            external_account_id=shop,
            state_hash=hash_token(raw_state),
            expires_at=expires_at,
        )
        self._db.add(oauth_state)
        self._db.commit()
        self._audit.record(
            actor_user_id=actor_user_id,
            action="connector.connection_created",
            target_type="CommerceOAuthState",
            target_id=str(oauth_state.id),
            company_id=tenant.company_id,
            metadata={"provider": "shopify"},
        )
        return CommerceAuthorizationStart(
            authorization_url=connector.authenticate(
                tenant_id=tenant.company_id,
                configuration={"shop_domain": shop, "state": raw_state},
            ),
            state=raw_state,
            expires_at=expires_at,
        )

    def begin_woocommerce_authorization(
        self,
        tenant: TenantContext,
        *,
        actor_user_id: UUID,
        store_url: str,
    ) -> CommerceAuthorizationStart:
        connector = self._woocommerce()
        normalized_store = connector.normalize_store_url(store_url)
        self._assert_store_tenant(tenant, "woocommerce", normalized_store)
        now = self._now()
        previous_states = self._db.scalars(
            select(CommerceOAuthState).where(
                CommerceOAuthState.company_id == tenant.company_id,
                CommerceOAuthState.provider == "woocommerce",
                CommerceOAuthState.external_account_id == normalized_store,
                CommerceOAuthState.consumed_at.is_(None),
            )
        ).all()
        for previous_state in previous_states:
            previous_state.consumed_at = now
        raw_state = secrets.token_urlsafe(48)
        expires_at = now + self._WOOCOMMERCE_STATE_TTL
        oauth_state = CommerceOAuthState(
            company_id=tenant.company_id,
            actor_user_id=actor_user_id,
            provider="woocommerce",
            external_account_id=normalized_store,
            state_hash=hash_token(raw_state),
            expires_at=expires_at,
        )
        connection = self._db.scalar(
            select(CommerceConnection).where(
                CommerceConnection.provider == "woocommerce",
                CommerceConnection.external_account_id == normalized_store,
                CommerceConnection.company_id == tenant.company_id,
            )
        )
        if connection is None:
            connection = CommerceConnection(
                company_id=tenant.company_id,
                provider="woocommerce",
                external_account_id=normalized_store,
                display_name=self._store_display_name(normalized_store),
                status=CommerceConnectionStatus.AUTHORIZING.value,
            )
            self._db.add(connection)
        else:
            previous_status = connection.status
            connection.status = CommerceConnectionStatus.AUTHORIZING.value
            connection.error_category = None
            connection.disconnected_at = None
            if previous_status in {
                CommerceConnectionStatus.FAILED.value,
                CommerceConnectionStatus.REAUTH_REQUIRED.value,
                CommerceConnectionStatus.DISCONNECTED.value,
            }:
                connection.encrypted_credentials = None
        self._db.add(oauth_state)
        self._db.commit()
        self._audit.record(
            actor_user_id=actor_user_id,
            action="connector.connection_created",
            target_type="CommerceOAuthState",
            target_id=str(oauth_state.id),
            company_id=tenant.company_id,
            metadata={"provider": "woocommerce"},
        )
        return CommerceAuthorizationStart(
            authorization_url=connector.authenticate(
                tenant_id=tenant.company_id,
                configuration={"store_url": normalized_store, "state": raw_state},
            ),
            state=raw_state,
            expires_at=expires_at,
        )

    async def complete_woocommerce_authorization(
        self,
        *,
        raw_state: str,
        callback_payload: Mapping[str, str],
    ) -> CommerceConnection:
        oauth_state = self._validate_woocommerce_state(raw_state, callback_payload)
        connector = self._woocommerce()
        try:
            returned = await connector.handle_oauth_callback(
                tenant_id=oauth_state.company_id,
                callback_parameters=callback_payload,
            )
            return self._persist_woocommerce_credentials(
                TenantContext(company_id=oauth_state.company_id),
                actor_user_id=oauth_state.actor_user_id,
                store_url=oauth_state.external_account_id,
                consumer_key=str(returned["consumer_key"]),
                consumer_secret=str(returned["consumer_secret"]),
                oauth_state=oauth_state,
            )
        except WooCommerceConnectorError as exc:
            self._mark_woocommerce_authorization_failed(
                oauth_state.company_id,
                oauth_state.external_account_id,
                exc,
            )
            raise CommerceAuthorizationError(self._woocommerce_auth_message(exc)) from exc

    async def connect_woocommerce_manual(
        self,
        tenant: TenantContext,
        *,
        actor_user_id: UUID,
        store_url: str,
        consumer_key: str,
        consumer_secret: str,
    ) -> CommerceConnection:
        connector = self._woocommerce()
        normalized_store = connector.normalize_store_url(store_url)
        if not consumer_key.strip().startswith("ck_") or not consumer_secret.strip().startswith(
            "cs_"
        ):
            raise CommerceAuthorizationError("Invalid WooCommerce credentials")
        self._assert_store_tenant(tenant, "woocommerce", normalized_store)
        try:
            return await self._authorize_woocommerce_credentials(
                tenant,
                actor_user_id=actor_user_id,
                store_url=normalized_store,
                consumer_key=consumer_key.strip(),
                consumer_secret=consumer_secret.strip(),
            )
        except WooCommerceConnectorError as exc:
            raise CommerceAuthorizationError(self._woocommerce_auth_message(exc)) from exc

    async def complete_shopify_oauth(
        self,
        callback_parameters: Mapping[str, str],
    ) -> CommerceConnection:
        raw_state = callback_parameters.get("state", "")
        oauth_state = self._db.scalar(
            select(CommerceOAuthState).where(
                CommerceOAuthState.provider == "shopify",
                CommerceOAuthState.state_hash == hash_token(raw_state),
                CommerceOAuthState.consumed_at.is_(None),
            )
        )
        now = self._now()
        if oauth_state is None or not raw_state or self._as_utc(oauth_state.expires_at) <= now:
            raise CommerceAuthorizationError("OAuth state is invalid or expired")

        connector = self._shopify()
        callback_shop = connector.normalize_shop_domain(
            callback_parameters.get("shop", "")
        )
        if not secrets.compare_digest(callback_shop, oauth_state.external_account_id):
            raise CommerceAuthorizationError("OAuth shop does not match the authorization request")

        oauth_state.consumed_at = now
        self._db.add(oauth_state)
        self._db.commit()

        credentials = await connector.handle_oauth_callback(
            tenant_id=oauth_state.company_id,
            callback_parameters=callback_parameters,
        )
        connection = self._db.scalar(
            select(CommerceConnection).where(
                CommerceConnection.provider == "shopify",
                CommerceConnection.external_account_id == callback_shop,
            )
        )
        if connection is not None and connection.company_id != oauth_state.company_id:
            raise CommerceAuthorizationError("This Shopify store already belongs to another tenant")
        if connection is None:
            connection = CommerceConnection(
                company_id=oauth_state.company_id,
                provider="shopify",
                external_account_id=callback_shop,
                encrypted_credentials="",
            )
            self._db.add(connection)
            self._db.flush()

        secret_payload = {
            "access_token": str(credentials["access_token"]),
            "refresh_token": str(credentials["refresh_token"]),
        }
        connection.encrypted_credentials = self._cipher.encrypt(secret_payload)
        connection.granted_scopes = [
            scope for scope in str(credentials.get("scope") or "").split(",") if scope
        ]
        connection.capabilities = sorted(
            capability.value for capability in connector.definition.capabilities
        )
        connection.status = CommerceConnectionStatus.CONNECTING.value
        connection.error_category = None
        connection.disconnected_at = None
        connection.access_token_expires_at = self._expires_at(
            now, credentials.get("expires_in")
        )
        connection.refresh_token_expires_at = self._expires_at(
            now, credentials.get("refresh_token_expires_in")
        )
        self._db.commit()

        context = self._context(connection, secret_payload)
        try:
            connected = await connector.test_connection(context)
        except ShopifyConnectorError as exc:
            connection.status = CommerceConnectionStatus.ERROR.value
            connection.error_category = "connection_test_failed"
            self._db.commit()
            raise CommerceAuthorizationError("Shopify connection test failed") from exc
        if not connected:
            connection.status = CommerceConnectionStatus.ERROR.value
            connection.error_category = "connection_test_failed"
            self._db.commit()
            raise CommerceAuthorizationError("Shopify connection test failed")

        self._audit.record(
            actor_user_id=oauth_state.actor_user_id,
            action="connector.connection_authorized",
            target_type="CommerceConnection",
            target_id=str(connection.id),
            company_id=connection.company_id,
            metadata={"provider": "shopify", "status": connection.status},
        )
        return connection

    def mark_setup_complete(
        self, tenant: TenantContext, connection_id: UUID
    ) -> CommerceConnection:
        connection = self.get_connection(tenant, connection_id)
        if connection.status != CommerceConnectionStatus.CONNECTING.value:
            raise CommerceConnectionError("Commerce connection setup is not in progress")
        connection.status = CommerceConnectionStatus.CONNECTED.value
        connection.error_category = None
        self._db.commit()
        return connection

    def list_connections(self, tenant: TenantContext) -> tuple[CommerceConnection, ...]:
        return tuple(
            self._db.scalars(
                select(CommerceConnection)
                .where(CommerceConnection.company_id == tenant.company_id)
                .order_by(CommerceConnection.created_at.desc())
            ).all()
        )

    def get_connection(
        self, tenant: TenantContext, connection_id: UUID
    ) -> CommerceConnection:
        connection = self._db.scalar(
            select(CommerceConnection).where(
                CommerceConnection.id == connection_id,
                CommerceConnection.company_id == tenant.company_id,
            )
        )
        if connection is None:
            raise CommerceConnectionNotFound("Commerce connection not found")
        return connection

    def mark_setup_failed(
        self,
        tenant: TenantContext,
        connection_id: UUID,
        *,
        error_category: str,
    ) -> CommerceConnection:
        connection = self.get_connection(tenant, connection_id)
        connection.status = CommerceConnectionStatus.ERROR.value
        connection.error_category = error_category
        connection.current_entity = None
        connection.sync_started_at = None
        self._db.commit()
        return connection

    def mark_setup_degraded(
        self,
        tenant: TenantContext,
        connection_id: UUID,
        *,
        error_category: str,
    ) -> CommerceConnection:
        connection = self.get_connection(tenant, connection_id)
        connection.status = CommerceConnectionStatus.DEGRADED.value
        connection.error_category = error_category
        connection.current_entity = None
        connection.sync_started_at = None
        self._db.commit()
        return connection

    def mark_woocommerce_setup_failed(
        self,
        tenant: TenantContext,
        connection_id: UUID,
        *,
        error_category: str,
        reauth_required: bool = False,
    ) -> CommerceConnection:
        connection = self.get_connection(tenant, connection_id)
        if connection.provider != "woocommerce":
            raise CommerceConnectionError("Connection is not a WooCommerce connection")
        connection.status = (
            CommerceConnectionStatus.REAUTH_REQUIRED.value
            if reauth_required
            else CommerceConnectionStatus.FAILED.value
        )
        connection.error_category = error_category
        connection.current_entity = None
        connection.sync_started_at = None
        self._db.commit()
        return connection

    async def sync_context(
        self, tenant: TenantContext, connection_id: UUID
    ) -> ConnectorSyncContext:
        connection = self.get_connection(tenant, connection_id)
        if (
            connection.status == CommerceConnectionStatus.DISCONNECTED.value
            or not connection.encrypted_credentials
        ):
            raise CommerceConnectionError("Commerce connection is disconnected")
        credentials = self._cipher.decrypt(connection.encrypted_credentials)
        if connection.provider == "woocommerce":
            if not credentials.get("consumer_key") or not credentials.get(
                "consumer_secret"
            ):
                raise CommerceAuthorizationError(
                    "WooCommerce reauthorization is required"
                )
            return self._context(connection, credentials)
        access_token = str(credentials.get("access_token") or "")
        refresh_token = str(credentials.get("refresh_token") or "")
        if connection.provider != "shopify":
            raise CommerceConnectionError("Commerce connector is not configured")
        if not access_token:
            raise CommerceConnectionError("Commerce connection credentials are missing")
        if (
            connection.access_token_expires_at is not None
            and self._as_utc(connection.access_token_expires_at)
            <= self._now() + self._REFRESH_MARGIN
        ):
            if not refresh_token:
                raise CommerceAuthorizationError("Shopify reauthorization is required")
            refreshed = await self._shopify().refresh_credentials(
                shop=connection.external_account_id,
                refresh_token=refresh_token,
            )
            access_token = str(refreshed.get("access_token") or "")
            refresh_token = str(refreshed.get("refresh_token") or "")
            if not access_token or not refresh_token:
                raise CommerceAuthorizationError("Shopify reauthorization is required")
            connection.encrypted_credentials = self._cipher.encrypt(
                {"access_token": access_token, "refresh_token": refresh_token}
            )
            now = self._now()
            connection.access_token_expires_at = self._expires_at(
                now, refreshed.get("expires_in")
            )
            connection.refresh_token_expires_at = self._expires_at(
                now, refreshed.get("refresh_token_expires_in")
            )
            self._db.commit()
        return self._context(
            connection,
            {"access_token": access_token, "refresh_token": refresh_token},
        )

    async def disconnect(
        self,
        tenant: TenantContext,
        connection_id: UUID,
        *,
        actor_user_id: UUID,
    ) -> CommerceConnection:
        connection = self.get_connection(tenant, connection_id)
        if connection.encrypted_credentials:
            credentials = self._cipher.decrypt(connection.encrypted_credentials)
            try:
                await self._registry.get(connection.provider).disconnect(
                    self._context(connection, credentials)
                )
            except (ShopifyConnectorError, WooCommerceConnectorError):
                logger.warning(
                    "Provider disconnect failed company=%s provider=%s connection=%s",
                    connection.company_id,
                    connection.provider,
                    connection.id,
                )
        connection.encrypted_credentials = None
        connection.status = CommerceConnectionStatus.DISCONNECTED.value
        connection.current_entity = None
        connection.disconnected_at = self._now()
        self._db.commit()
        self._audit.record(
            actor_user_id=actor_user_id,
            action="connector.connection_disconnected",
            target_type="CommerceConnection",
            target_id=str(connection.id),
            company_id=connection.company_id,
            metadata={"provider": connection.provider},
        )
        return connection

    def _shopify(self) -> ShopifyConnector:
        connector = self._registry.get("shopify")
        if not isinstance(connector, ShopifyConnector):
            raise CommerceConnectionError("Shopify connector is not configured")
        return connector

    def _woocommerce(self) -> WooCommerceConnector:
        connector = self._registry.get("woocommerce")
        if not isinstance(connector, WooCommerceConnector):
            raise CommerceConnectionError("WooCommerce connector is not configured")
        return connector

    async def _authorize_woocommerce_credentials(
        self,
        tenant: TenantContext,
        *,
        actor_user_id: UUID,
        store_url: str,
        consumer_key: str,
        consumer_secret: str,
    ) -> CommerceConnection:
        connector = self._woocommerce()
        self._assert_store_tenant(tenant, "woocommerce", store_url)
        credentials = {
            "consumer_key": consumer_key,
            "consumer_secret": consumer_secret,
            "webhook_secret": secrets.token_urlsafe(48),
        }
        existing = self._db.scalar(
            select(CommerceConnection).where(
                CommerceConnection.provider == "woocommerce",
                CommerceConnection.external_account_id == store_url,
                CommerceConnection.company_id == tenant.company_id,
            )
        )
        connection_id = existing.id if existing is not None else uuid4()
        context = ConnectorSyncContext(
            tenant_id=tenant.company_id,
            connection_id=connection_id,
            access_token="",
            external_account_id=store_url,
            credentials=credentials,
        )
        if not await connector.test_connection(context):
            raise WooCommerceAuthenticationError(
                "WooCommerce connection validation failed"
            )
        return self._persist_woocommerce_credentials(
            tenant,
            actor_user_id=actor_user_id,
            store_url=store_url,
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
            connection_id=connection_id,
        )

    def _persist_woocommerce_credentials(
        self,
        tenant: TenantContext,
        *,
        actor_user_id: UUID,
        store_url: str,
        consumer_key: str,
        consumer_secret: str,
        connection_id: UUID | None = None,
        oauth_state: CommerceOAuthState | None = None,
    ) -> CommerceConnection:
        connector = self._woocommerce()
        self._assert_store_tenant(tenant, "woocommerce", store_url)
        credentials = {
            "consumer_key": consumer_key,
            "consumer_secret": consumer_secret,
            "webhook_secret": secrets.token_urlsafe(48),
        }
        existing = self._db.scalar(
            select(CommerceConnection).where(
                CommerceConnection.provider == "woocommerce",
                CommerceConnection.external_account_id == store_url,
                CommerceConnection.company_id == tenant.company_id,
            )
        )
        resolved_connection_id = (
            existing.id if existing is not None else connection_id or uuid4()
        )
        connection = existing or CommerceConnection(
            id=resolved_connection_id,
            company_id=tenant.company_id,
            provider="woocommerce",
            external_account_id=store_url,
        )
        if existing is None:
            self._db.add(connection)
        connection.display_name = self._store_display_name(store_url)
        connection.encrypted_credentials = self._cipher.encrypt(credentials)
        connection.granted_scopes = ["read_write"]
        connection.capabilities = sorted(
            capability.value for capability in connector.definition.capabilities
        )
        connection.status = CommerceConnectionStatus.CONNECTING.value
        connection.error_category = None
        connection.disconnected_at = None
        connection.access_token_expires_at = None
        connection.refresh_token_expires_at = None
        if oauth_state is not None:
            oauth_state.consumed_at = self._now()
            self._db.add(oauth_state)
        self._db.commit()
        self._audit.record(
            actor_user_id=actor_user_id,
            action="connector.connection_authorized",
            target_type="CommerceConnection",
            target_id=str(connection.id),
            company_id=tenant.company_id,
            metadata={"provider": "woocommerce", "status": connection.status},
        )
        return connection

    def _validate_woocommerce_state(
        self,
        raw_state: str,
        callback_payload: Mapping[str, str],
    ) -> CommerceOAuthState:
        oauth_state = self._db.scalar(
            select(CommerceOAuthState).where(
                CommerceOAuthState.provider == "woocommerce",
                CommerceOAuthState.state_hash == hash_token(raw_state),
                CommerceOAuthState.consumed_at.is_(None),
            ).with_for_update()
        )
        now = self._now()
        returned_state = str(callback_payload.get("user_id") or "")
        if (
            oauth_state is None
            or not raw_state
            or not secrets.compare_digest(returned_state, raw_state)
            or self._as_utc(oauth_state.expires_at) <= now
        ):
            raise CommerceAuthorizationError("Authorization state is invalid or expired")
        return oauth_state

    def _assert_store_tenant(
        self,
        tenant: TenantContext,
        provider: str,
        external_account_id: str,
    ) -> None:
        connection = self._db.scalar(
            select(CommerceConnection).where(
                CommerceConnection.provider == provider,
                CommerceConnection.external_account_id == external_account_id,
            )
        )
        if connection is not None and connection.company_id != tenant.company_id:
            raise CommerceAuthorizationError(
                "This WooCommerce store already belongs to another tenant"
            )

    def _mark_woocommerce_authorization_failed(
        self,
        company_id: UUID,
        store_url: str,
        error: WooCommerceConnectorError,
    ) -> None:
        connection = self._db.scalar(
            select(CommerceConnection).where(
                CommerceConnection.provider == "woocommerce",
                CommerceConnection.external_account_id == store_url,
                CommerceConnection.company_id == company_id,
            )
        )
        if connection is None:
            return
        connection.status = (
            CommerceConnectionStatus.REAUTH_REQUIRED.value
            if isinstance(error, WooCommerceAuthenticationError)
            else CommerceConnectionStatus.FAILED.value
        )
        connection.error_category = (
            "insufficient_permissions"
            if isinstance(error, WooCommercePermissionError)
            else "authorization_failed"
        )
        self._db.commit()

    @staticmethod
    def _woocommerce_auth_message(error: WooCommerceConnectorError) -> str:
        if isinstance(error, WooCommercePermissionError):
            return "WooCommerce permissions are insufficient"
        if isinstance(error, WooCommerceAuthenticationError):
            return "WooCommerce authentication was rejected"
        return "WooCommerce connection validation failed"

    @staticmethod
    def _store_display_name(store_url: str) -> str:
        parsed = urlsplit(store_url)
        return f"{parsed.hostname or ''}{parsed.path.rstrip('/')}"

    @staticmethod
    def _context(
        connection: CommerceConnection,
        credentials: Mapping[str, Any],
    ) -> ConnectorSyncContext:
        return ConnectorSyncContext(
            tenant_id=connection.company_id,
            connection_id=connection.id,
            access_token=str(credentials.get("access_token") or ""),
            external_account_id=connection.external_account_id,
            credentials=dict(credentials),
        )

    @staticmethod
    def _expires_at(now: datetime, seconds: Any) -> datetime | None:
        try:
            duration = int(seconds or 0)
        except (TypeError, ValueError):
            return None
        return now + timedelta(seconds=duration) if duration > 0 else None

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)