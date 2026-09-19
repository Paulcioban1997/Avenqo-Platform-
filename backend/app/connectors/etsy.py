"""Etsy v3 Open API marketplace connector conforming to CommerceConnector contract."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlencode
from uuid import UUID

import httpx

from shared.ai_engine.connectors.catalog import COMMERCE_CONNECTOR_CATALOG
from shared.ai_engine.connectors.commerce import (
    CommerceConnector,
    ConnectorPage,
    ConnectorSyncContext,
)

logger = logging.getLogger("avenqo.connectors.etsy")


class EtsyConnectorError(RuntimeError):
    pass


class EtsyAuthenticationError(EtsyConnectorError):
    pass


class EtsyTemporaryError(EtsyConnectorError):
    pass


class EtsyConnector(CommerceConnector):
    definition = next(
        item for item in COMMERCE_CONNECTOR_CATALOG if item.provider == "etsy"
    )

    _OAUTH_AUTHORIZE_URL = "https://www.etsy.com/oauth/connect"
    _OAUTH_TOKEN_URL = "https://api.etsy.com/v3/public/oauth/token"
    _API_BASE_URL = "https://openapi.etsy.com/v3"
    _SCOPES = (
        "listings_r",
        "transactions_r",
        "shops_r",
        "profile_r",
    )

    def __init__(
        self,
        *,
        client_id: str = "avenqo_etsy_app",
        callback_uri: str = "https://avenqo.ca/api/v1/commerce/oauth/etsy/callback",
        http_client: httpx.AsyncClient | None = None,
        page_size: int = 100,
    ) -> None:
        self._client_id = client_id
        self._callback_uri = callback_uri
        self._http_client = http_client
        self._page_size = page_size

    def _client(self) -> httpx.AsyncClient:
        """Return the injected client (for tests) or create a fresh one."""
        return self._http_client or httpx.AsyncClient(timeout=20.0)

    @staticmethod
    def generate_pkce_pair() -> tuple[str, str]:
        """Generate code_verifier and code_challenge for OAuth2 PKCE."""
        verifier = secrets.token_urlsafe(64)
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
        return verifier, challenge

    def authenticate(
        self, *, tenant_id: UUID, configuration: Mapping[str, str]
    ) -> str:
        state = configuration.get("state", "").strip()
        code_challenge = configuration.get("code_challenge", "").strip()
        if not state:
            raise EtsyAuthenticationError("Authorization state is required")

        params = {
            "response_type": "code",
            "client_id": configuration.get("client_id") or self._client_id,
            "redirect_uri": configuration.get("redirect_uri") or self._callback_uri,
            "scope": " ".join(self._SCOPES),
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        return f"{self._OAUTH_AUTHORIZE_URL}?{urlencode(params)}"

    async def handle_oauth_callback(
        self,
        *,
        tenant_id: UUID,
        callback_parameters: Mapping[str, str],
    ) -> Mapping[str, Any]:
        code = callback_parameters.get("code")
        verifier = callback_parameters.get("code_verifier")
        client_id = callback_parameters.get("client_id") or self._client_id
        redirect_uri = callback_parameters.get("redirect_uri") or self._callback_uri

        if not code:
            raise EtsyAuthenticationError("Authorization code missing from callback")

        payload = {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code": code,
            "code_verifier": verifier or "",
        }

        client = self._client()
        try:
            resp = await client.post(self._OAUTH_TOKEN_URL, data=payload)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            logger.error("Etsy OAuth token exchange failed: %s", exc)
            raise EtsyAuthenticationError(f"Failed to exchange Etsy token: {exc}") from exc
        finally:
            if self._http_client is None:
                await client.aclose()

        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")
        expires_in = data.get("expires_in", 3600)
        account_id = data.get("user_id") or "etsy_shop"

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": expires_in,
            "client_id": client_id,
            "account_id": str(account_id),
        }

    async def refresh_credentials(
        self, credentials: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        refresh_token = credentials.get("refresh_token")
        client_id = credentials.get("client_id") or self._client_id
        if not refresh_token:
            raise EtsyAuthenticationError("Missing refresh token")

        payload = {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": refresh_token,
        }

        client = self._client()
        try:
            resp = await client.post(self._OAUTH_TOKEN_URL, data=payload)
            resp.raise_for_status()
            data = resp.json()
            return {
                **dict(credentials),
                "access_token": data.get("access_token"),
                "refresh_token": data.get("refresh_token", refresh_token),
                "expires_in": data.get("expires_in", 3600),
            }
        except httpx.HTTPError as exc:
            raise EtsyAuthenticationError(f"Failed to refresh Etsy token: {exc}") from exc
        finally:
            if self._http_client is None:
                await client.aclose()

    async def test_connection(self, context: ConnectorSyncContext) -> bool:
        if not context.access_token:
            return False
        headers = {
            "Authorization": f"Bearer {context.access_token}",
            "x-api-key": str(context.credentials.get("client_id") or self._client_id),
        }
        client = self._client()
        try:
            resp = await client.get(
                f"{self._API_BASE_URL}/application/openapi-ping",
                headers=headers,
            )
            return resp.status_code in {200, 204}
        except httpx.HTTPError:
            return False
        finally:
            if self._http_client is None:
                await client.aclose()

    async def sync_orders(self, context: ConnectorSyncContext) -> ConnectorPage:
        """Fetch shop receipts/orders from Etsy v3."""
        shop_id = context.external_account_id
        headers = {
            "Authorization": f"Bearer {context.access_token}",
            "x-api-key": str(context.credentials.get("client_id") or self._client_id),
        }
        limit = self._page_size
        offset = int(context.cursor or 0)
        url = f"{self._API_BASE_URL}/application/shops/{shop_id}/receipts"
        params = {"limit": limit, "offset": offset}
        if context.updated_since:
            params["min_last_modified"] = context.updated_since

        client = self._client()
        try:
            resp = await client.get(url, headers=headers, params=params)
            if resp.status_code == 200:
                data = resp.json()
                results = tuple(data.get("results") or ())
                count = data.get("count", 0)
                next_cursor = str(offset + limit) if (offset + limit < count) else None
                return ConnectorPage(results, next_cursor)
            return ConnectorPage((), None)
        except httpx.HTTPError:
            return ConnectorPage((), None)
        finally:
            if self._http_client is None:
                await client.aclose()

    async def sync_products(self, context: ConnectorSyncContext) -> ConnectorPage:
        """Fetch active listings from Etsy shop."""
        shop_id = context.external_account_id
        headers = {
            "Authorization": f"Bearer {context.access_token}",
            "x-api-key": str(context.credentials.get("client_id") or self._client_id),
        }
        limit = self._page_size
        offset = int(context.cursor or 0)
        url = f"{self._API_BASE_URL}/application/shops/{shop_id}/listings/active"
        params = {"limit": limit, "offset": offset}

        client = self._client()
        try:
            resp = await client.get(url, headers=headers, params=params)
            if resp.status_code == 200:
                data = resp.json()
                results = tuple(data.get("results") or ())
                count = data.get("count", 0)
                next_cursor = str(offset + limit) if (offset + limit < count) else None
                return ConnectorPage(results, next_cursor)
            return ConnectorPage((), None)
        except httpx.HTTPError:
            return ConnectorPage((), None)
        finally:
            if self._http_client is None:
                await client.aclose()

    async def sync_inventory(self, context: ConnectorSyncContext) -> ConnectorPage:
        """Extract inventory levels from listings."""
        products_page = await self.sync_products(context)
        items = []
        for p in products_page.records:
            items.append(
                {
                    "inventory_item_id": str(p.get("listing_id")),
                    "product_id": str(p.get("listing_id")),
                    "sku": str(p.get("sku") or p.get("listing_id") or ""),
                    "stock_quantity": p.get("quantity", 0),
                    "inventory_level": p.get("quantity", 0),
                    "updated_at": p.get("updated_timestamp"),
                }
            )
        return ConnectorPage(tuple(items), products_page.next_cursor)

    async def sync_customers(self, context: ConnectorSyncContext) -> ConnectorPage:
        """Extract customer/buyer profiles from receipts."""
        orders_page = await self.sync_orders(context)
        customers = []
        seen = set()
        for o in orders_page.records:
            buyer_id = str(o.get("buyer_user_id") or "")
            if buyer_id and buyer_id not in seen:
                seen.add(buyer_id)
                customers.append(
                    {
                        "customer_id": buyer_id,
                        "email": str(o.get("buyer_email") or ""),
                        "first_name": str(o.get("name") or ""),
                        "last_name": "",
                        "country": str(o.get("country_iso") or ""),
                        "orders_count": 1,
                        "created_at": o.get("created_timestamp"),
                        "updated_at": o.get("updated_timestamp"),
                    }
                )
        return ConnectorPage(tuple(customers), None)

    async def initial_sync(
        self, context: ConnectorSyncContext
    ) -> Mapping[str, tuple[Mapping[str, Any], ...]]:
        orders = await self.sync_orders(context)
        products = await self.sync_products(context)
        inventory = await self.sync_inventory(context)
        customers = await self.sync_customers(context)
        return {
            "orders": orders.records,
            "products": products.records,
            "inventory": inventory.records,
            "customers": customers.records,
            "refunds": (),
        }

    async def incremental_sync(
        self, context: ConnectorSyncContext
    ) -> Mapping[str, tuple[Mapping[str, Any], ...]]:
        return await self.initial_sync(context)

    async def get_sync_status(self, context: ConnectorSyncContext) -> str:
        try:
            return "CONNECTED" if await self.test_connection(context) else "FAILED"
        except Exception:
            return "FAILED"

    async def disconnect(self, context: ConnectorSyncContext) -> None:
        """Revoke authorization if Etsy API endpoint allows."""
        pass
