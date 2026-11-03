"""Google Ads connector implementation using Google Ads API v26."""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from backend.app.connectors.ads.base import (
    AdCampaign,
    AdsConfigurationMissingError,
    AdsConnectorError,
    AdsPerformanceSummary,
    BaseAdsConnector,
    resolve_date_range,
)

logger = logging.getLogger("avenqo.ads.google")


def _redact_secrets(text: str) -> str:
    """Masks authorization tokens, client secrets, and sensitive credentials in logs/exceptions."""
    sanitized = re.sub(r"(Bearer\s+)[A-Za-z0-9._\-]+", r"\1[REDACTED]", text)
    sanitized = re.sub(r"(client_secret=)[^&]+", r"\1[REDACTED]", sanitized)
    sanitized = re.sub(r"(developer-token:\s*)[^\s,]+", r"\1[REDACTED]", sanitized, flags=re.IGNORECASE)
    return sanitized


class GoogleAdsConnector(BaseAdsConnector):
    """Integrates with Google Ads API v26 in strict read-only mode."""

    OAUTH_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
    OAUTH_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
    API_VERSION = "v26"
    GOOGLE_ADS_API_BASE = f"https://googleads.googleapis.com/{API_VERSION}"
    SCOPE = "https://www.googleapis.com/auth/adwords"

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        developer_token: str | None = None,
        redirect_uri: str | None = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.developer_token = developer_token
        self.redirect_uri = redirect_uri

    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.redirect_uri)

    def is_api_ready(self) -> bool:
        return bool(self.is_configured() and self.developer_token)

    def get_auth_url(self, company_id: UUID, user_id: UUID, state: str) -> str:
        if not self.is_configured():
            raise AdsConfigurationMissingError(
                "Google Ads",
                "GOOGLE_ADS_CLIENT_ID, GOOGLE_ADS_CLIENT_SECRET ou GOOGLE_ADS_REDIRECT_URI non configurés."
            )
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": self.SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
            "include_granted_scopes": "true",
        }
        return f"{self.OAUTH_AUTH_ENDPOINT}?{urllib.parse.urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str | None = None) -> dict[str, Any]:
        if not self.is_configured():
            raise AdsConfigurationMissingError("Google Ads")

        target_redirect = redirect_uri or self.redirect_uri
        payload = urllib.parse.urlencode({
            "code": code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": target_redirect,
            "grant_type": "authorization_code",
        }).encode("utf-8")

        req = urllib.request.Request(
            self.OAUTH_TOKEN_ENDPOINT,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                err_body = json.loads(exc.read().decode("utf-8"))
                err_msg = err_body.get("error_description") or err_body.get("error") or str(exc)
            except Exception:
                err_msg = str(exc)
            raise AdsConnectorError(
                _redact_secrets(f"Échec échange de code Google Ads: {err_msg}"),
                code="GOOGLE_ADS_EXCHANGE_FAILED"
            )
        except Exception as exc:
            raise AdsConnectorError(
                _redact_secrets(f"Erreur réseau Google Ads: {exc}"),
                code="GOOGLE_ADS_NETWORK_ERROR"
            )

        return {
            "access_token": data.get("access_token"),
            "refresh_token": data.get("refresh_token"),
            "expires_in": data.get("expires_in", 3600),
            "token_type": data.get("token_type", "Bearer"),
            "scope": data.get("scope", self.SCOPE),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    async def refresh_token(self, credentials: dict[str, Any]) -> dict[str, Any]:
        refresh_tok = credentials.get("refresh_token")
        if not refresh_tok:
            raise AdsConnectorError("Aucun refresh_token disponible pour Google Ads.", code="NO_REFRESH_TOKEN")

        payload = urllib.parse.urlencode({
            "refresh_token": refresh_tok,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "refresh_token",
        }).encode("utf-8")

        req = urllib.request.Request(
            self.OAUTH_TOKEN_ENDPOINT,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in (400, 401):
                raise AdsConnectorError(
                    "Le jeton Google Ads a été révoqué ou a expiré. Reconnexion requise.",
                    code="TOKEN_REVOKED",
                    status_code=401,
                )
            raise AdsConnectorError(
                _redact_secrets(f"Échec rafraîchissement token Google Ads ({exc.code}): {exc.reason}"),
                code="GOOGLE_ADS_REFRESH_FAILED"
            )
        except Exception as exc:
            raise AdsConnectorError(
                _redact_secrets(f"Échec rafraîchissement token Google Ads: {exc}"),
                code="GOOGLE_ADS_REFRESH_FAILED"
            )

        updated = dict(credentials)
        updated["access_token"] = data.get("access_token")
        updated["expires_in"] = data.get("expires_in", 3600)
        updated["updated_at"] = datetime.now(timezone.utc).isoformat()
        return updated

    async def verify_access(self, credentials: dict[str, Any], account_id: str | None = None) -> dict[str, Any]:
        """Validates that credentials can read accessible customer accounts and gets currency/metadata."""
        if not self.developer_token:
            raise AdsConfigurationMissingError(
                "Google Ads",
                "GOOGLE_ADS_DEVELOPER_TOKEN requis pour interroger l'API Google Ads. Statut : BLOCKED."
            )

        access_token = credentials.get("access_token")
        headers = {
            "Authorization": f"Bearer {access_token}",
            "developer-token": self.developer_token,
            "Content-Type": "application/json",
        }

        # 1. List accessible customers
        list_url = f"{self.GOOGLE_ADS_API_BASE}/customers:listAccessibleCustomers"
        req = urllib.request.Request(list_url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise AdsConnectorError("Accès Google Ads non autorisé ou token expiré.", code="TOKEN_REVOKED", status_code=401)
            raise AdsConnectorError(_redact_secrets(f"Erreur vérification Google Ads ({exc.code}): {exc.reason}"), code="GOOGLE_ADS_API_ERROR")
        except Exception as exc:
            raise AdsConnectorError(_redact_secrets(f"Erreur réseau vérification Google Ads: {exc}"), code="GOOGLE_ADS_NETWORK_ERROR")

        resource_names = data.get("resourceNames", [])
        accessible_ids = [r.replace("customers/", "").strip() for r in resource_names]

        target_id = (account_id or credentials.get("customer_id") or "").replace("-", "").strip()
        if target_id and accessible_ids and target_id not in accessible_ids:
            raise AdsConnectorError(
                f"Le compte client Google Ads {target_id} n'appartient pas aux comptes accessibles par cet utilisateur.",
                code="ACCOUNT_ACCESS_DENIED",
                status_code=403,
            )

        chosen_id = target_id or (accessible_ids[0] if accessible_ids else "")
        if not chosen_id:
            return {
                "accessible_ids": accessible_ids,
                "verified": False,
                "currency": "CAD",
                "account_name": None,
                "status": "PENDING_SELECT",
            }

        # 2. Query account currency and metadata via GAQL
        gaql = "SELECT customer.id, customer.descriptive_name, customer.currency_code, customer.time_zone, customer.status FROM customer LIMIT 1"
        search_url = f"{self.GOOGLE_ADS_API_BASE}/customers/{chosen_id}/googleAds:search"
        search_req = urllib.request.Request(
            search_url,
            data=json.dumps({"query": gaql}).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(search_req, timeout=15) as resp:
                customer_data = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            logger.warning("Impossible de lire les métadonnées du compte client %s: %s", chosen_id, _redact_secrets(str(exc)))
            return {
                "accessible_ids": accessible_ids,
                "customer_id": chosen_id,
                "verified": True,
                "currency": "CAD",
                "account_name": f"Google Ads ({chosen_id})",
                "status": "ACTIVE",
            }

        results = customer_data.get("results", [])
        cust = results[0].get("customer", {}) if results else {}
        currency = cust.get("currencyCode") or "CAD"
        name = cust.get("descriptiveName") or f"Google Ads ({chosen_id})"

        return {
            "accessible_ids": accessible_ids,
            "customer_id": chosen_id,
            "verified": True,
            "currency": currency,
            "account_name": name,
            "time_zone": cust.get("timeZone"),
            "status": cust.get("status", "ACTIVE"),
        }

    async def list_campaigns(
        self, credentials: dict[str, Any], account_id: str | None = None, period: str = "last_30d"
    ) -> list[AdCampaign]:
        if not self.developer_token:
            raise AdsConfigurationMissingError(
                "Google Ads",
                "GOOGLE_ADS_DEVELOPER_TOKEN requis pour interroger l'API Google Ads. Statut : BLOCKED."
            )

        customer_id = (account_id or credentials.get("customer_id") or "").replace("-", "").strip()
        if not customer_id:
            return []

        start_date, end_date = resolve_date_range(period)
        access_token = credentials.get("access_token")
        url = f"{self.GOOGLE_ADS_API_BASE}/customers/{customer_id}/googleAds:search"
        
        # Determine account native currency
        account_currency = credentials.get("currency") or "CAD"

        gaql = (
            "SELECT campaign.id, campaign.name, campaign.status, campaign_budget.amount_micros, "
            "metrics.cost_micros, metrics.impressions, metrics.clicks, metrics.conversions, "
            "metrics.conversions_value, customer.currency_code "
            f"FROM campaign WHERE segments.date BETWEEN '{start_date}' AND '{end_date}' "
            "ORDER BY metrics.cost_micros DESC LIMIT 50"
        )
        headers = {
            "Authorization": f"Bearer {access_token}",
            "developer-token": self.developer_token,
            "Content-Type": "application/json",
        }
        if credentials.get("login_customer_id"):
            headers["login-customer-id"] = credentials["login_customer_id"]

        campaigns: list[AdCampaign] = []
        page_token: str | None = None
        max_pages = 5

        for _ in range(max_pages):
            body_payload: dict[str, Any] = {"query": gaql, "pageSize": 50}
            if page_token:
                body_payload["pageToken"] = page_token

            req = urllib.request.Request(url, data=json.dumps(body_payload).encode("utf-8"), headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                if exc.code == 401:
                    raise AdsConnectorError("Jeton d'accès Google Ads révoqué ou expiré.", code="TOKEN_REVOKED", status_code=401)
                raise AdsConnectorError(_redact_secrets(f"Erreur API Google Ads ({exc.code}): {exc.reason}"), code="GOOGLE_ADS_API_ERROR")
            except Exception as exc:
                raise AdsConnectorError(_redact_secrets(f"Erreur réseau Google Ads: {exc}"), code="GOOGLE_ADS_NETWORK_ERROR")

            for row in data.get("results", []):
                camp = row.get("campaign", {})
                metrics = row.get("metrics", {})
                budget = row.get("campaignBudget", {})
                cust = row.get("customer", {})
                row_currency = cust.get("currencyCode") or account_currency

                cost_micros = int(metrics.get("costMicros", 0))
                spend = Decimal(cost_micros) / Decimal(1_000_000)
                budget_micros = int(budget.get("amountMicros", 0)) if budget.get("amountMicros") else None
                daily_budget = (Decimal(budget_micros) / Decimal(1_000_000)) if budget_micros is not None else None

                impressions = int(metrics.get("impressions", 0))
                clicks = int(metrics.get("clicks", 0))
                conversions = int(float(metrics.get("conversions", 0)))
                conversions_value = Decimal(str(metrics.get("conversionsValue", 0)))
                ctr = (clicks / impressions * 100) if impressions > 0 else 0.0
                cpc = (spend / Decimal(clicks)) if clicks > 0 else Decimal("0.00")
                roas = float(conversions_value / spend) if spend > Decimal("0.00") else 0.0

                campaigns.append(AdCampaign(
                    id=str(camp.get("id", "")),
                    name=camp.get("name", "Campagne Google Ads"),
                    status=camp.get("status", "UNKNOWN"),
                    provider="google_ads",
                    currency=row_currency,
                    daily_budget_native=daily_budget,
                    spend_native=spend.quantize(Decimal("0.01")),
                    impressions=impressions,
                    clicks=clicks,
                    conversions=conversions,
                    ctr=round(ctr, 2),
                    cpc_native=cpc.quantize(Decimal("0.01")),
                    roas=round(roas, 2),
                ))

            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return campaigns

    async def get_performance(
        self, credentials: dict[str, Any], account_id: str | None = None, period: str = "last_30d"
    ) -> AdsPerformanceSummary:
        campaigns = await self.list_campaigns(credentials, account_id, period)
        start_date, end_date = resolve_date_range(period)
        customer_id = (account_id or credentials.get("customer_id") or "").replace("-", "").strip()

        if not campaigns:
            native_curr = credentials.get("currency") or "CAD"
            return AdsPerformanceSummary(
                provider="google_ads",
                account_id=customer_id,
                native_currency=native_curr,
                period=period,
                start_date=start_date,
                end_date=end_date,
            )

        native_curr = campaigns[0].currency
        total_spend = sum((c.spend_native for c in campaigns), Decimal("0.00"))
        total_impressions = sum(c.impressions for c in campaigns)
        total_clicks = sum(c.clicks for c in campaigns)
        total_conversions = sum(c.conversions for c in campaigns)
        avg_ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0.0
        avg_cpc = (total_spend / Decimal(total_clicks)) if total_clicks > 0 else Decimal("0.00")

        return AdsPerformanceSummary(
            provider="google_ads",
            account_id=customer_id,
            native_currency=native_curr,
            total_spend_native=total_spend.quantize(Decimal("0.01")),
            total_impressions=total_impressions,
            total_clicks=total_clicks,
            total_conversions=total_conversions,
            average_ctr=round(avg_ctr, 2),
            average_cpc_native=avg_cpc.quantize(Decimal("0.01")),
            campaigns_count=len(campaigns),
            active_campaigns_count=sum(1 for c in campaigns if c.status == "ENABLED"),
            period=period,
            start_date=start_date,
            end_date=end_date,
        )
