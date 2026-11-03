"""Google Ads connector implementation using Google Ads API v18."""

from __future__ import annotations

import json
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
)


class GoogleAdsConnector(BaseAdsConnector):
    """Integrates with Google Ads API in strict read-only mode."""

    OAUTH_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
    OAUTH_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
    GOOGLE_ADS_API_BASE = "https://googleads.googleapis.com/v18"
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
            raise AdsConnectorError(f"Échec échange de code Google Ads: {err_msg}", code="GOOGLE_ADS_EXCHANGE_FAILED")
        except Exception as exc:
            raise AdsConnectorError(f"Erreur réseau Google Ads: {exc}", code="GOOGLE_ADS_NETWORK_ERROR")

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
        except Exception as exc:
            raise AdsConnectorError(f"Échec rafraîchissement token Google Ads: {exc}", code="GOOGLE_ADS_REFRESH_FAILED")

        updated = dict(credentials)
        updated["access_token"] = data.get("access_token")
        updated["expires_in"] = data.get("expires_in", 3600)
        updated["updated_at"] = datetime.now(timezone.utc).isoformat()
        return updated

    async def list_campaigns(self, credentials: dict[str, Any], account_id: str | None = None) -> list[AdCampaign]:
        if not self.developer_token:
            raise AdsConfigurationMissingError(
                "Google Ads",
                "GOOGLE_ADS_DEVELOPER_TOKEN requis pour interroger l'API Google Ads. Statut : BLOCKED."
            )

        customer_id = (account_id or credentials.get("customer_id") or "").replace("-", "").strip()
        if not customer_id:
            return []

        access_token = credentials.get("access_token")
        url = f"{self.GOOGLE_ADS_API_BASE}/customers/{customer_id}/googleAds:search"
        gaql = (
            "SELECT campaign.id, campaign.name, campaign.status, campaign_budget.amount_micros, "
            "metrics.cost_micros, metrics.impressions, metrics.clicks, metrics.conversions "
            "FROM campaign WHERE segments.date DURING LAST_30_DAYS ORDER BY metrics.cost_micros DESC LIMIT 50"
        )
        body = json.dumps({"query": gaql}).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {access_token}",
            "developer-token": self.developer_token,
            "Content-Type": "application/json",
        }
        if credentials.get("login_customer_id"):
            headers["login-customer-id"] = credentials["login_customer_id"]

        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise AdsConnectorError(f"Erreur API Google Ads ({exc.code}): {exc.reason}", code="GOOGLE_ADS_API_ERROR")
        except Exception as exc:
            raise AdsConnectorError(f"Erreur réseau Google Ads: {exc}", code="GOOGLE_ADS_NETWORK_ERROR")

        campaigns: list[AdCampaign] = []
        for row in data.get("results", []):
            camp = row.get("campaign", {})
            metrics = row.get("metrics", {})
            budget = row.get("campaignBudget", {})

            cost_micros = int(metrics.get("costMicros", 0))
            spend = Decimal(cost_micros) / Decimal(1_000_000)
            budget_micros = int(budget.get("amountMicros", 0)) if budget.get("amountMicros") else None
            daily_budget = (Decimal(budget_micros) / Decimal(1_000_000)) if budget_micros is not None else None

            impressions = int(metrics.get("impressions", 0))
            clicks = int(metrics.get("clicks", 0))
            conversions = int(float(metrics.get("conversions", 0)))
            ctr = (clicks / impressions * 100) if impressions > 0 else 0.0
            cpc = (spend / Decimal(clicks)) if clicks > 0 else Decimal("0.00")

            campaigns.append(AdCampaign(
                id=str(camp.get("id", "")),
                name=camp.get("name", "Campagne Google Ads"),
                status=camp.get("status", "UNKNOWN"),
                provider="google_ads",
                daily_budget_cad=daily_budget,
                spend_cad=spend.quantize(Decimal("0.01")),
                impressions=impressions,
                clicks=clicks,
                conversions=conversions,
                ctr=round(ctr, 2),
                cpc_cad=cpc.quantize(Decimal("0.01")),
            ))
        return campaigns

    async def get_performance(
        self, credentials: dict[str, Any], account_id: str | None = None, period: str = "last_30d"
    ) -> AdsPerformanceSummary:
        campaigns = await self.list_campaigns(credentials, account_id)
        total_spend = sum((c.spend_cad for c in campaigns), Decimal("0.00"))
        total_impressions = sum(c.impressions for c in campaigns)
        total_clicks = sum(c.clicks for c in campaigns)
        total_conversions = sum(c.conversions for c in campaigns)

        avg_ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0.0
        avg_cpc = (total_spend / Decimal(total_clicks)) if total_clicks > 0 else Decimal("0.00")
        active_count = sum(1 for c in campaigns if c.status == "ENABLED")

        return AdsPerformanceSummary(
            provider="google_ads",
            total_spend_cad=total_spend.quantize(Decimal("0.01")),
            total_impressions=total_impressions,
            total_clicks=total_clicks,
            total_conversions=total_conversions,
            average_ctr=round(avg_ctr, 2),
            average_cpc_cad=avg_cpc.quantize(Decimal("0.01")),
            campaigns_count=len(campaigns),
            active_campaigns_count=active_count,
            period=period,
        )

