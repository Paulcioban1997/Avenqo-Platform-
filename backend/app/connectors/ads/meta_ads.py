"""Meta Ads (Facebook / Instagram) connector implementation using Meta Graph API v20.0."""

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


class MetaAdsConnector(BaseAdsConnector):
    """Integrates with Meta Marketing Graph API in strict read-only mode."""

    OAUTH_AUTH_ENDPOINT = "https://www.facebook.com/v20.0/dialog/oauth"
    OAUTH_TOKEN_ENDPOINT = "https://graph.facebook.com/v20.0/oauth/access_token"
    GRAPH_API_BASE = "https://graph.facebook.com/v20.0"
    DEFAULT_SCOPES = ["ads_read", "read_insights"]

    def __init__(
        self,
        app_id: str | None = None,
        app_secret: str | None = None,
        redirect_uri: str | None = None,
    ) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.redirect_uri = redirect_uri

    def is_configured(self) -> bool:
        return bool(self.app_id and self.app_secret and self.redirect_uri)

    def get_auth_url(self, company_id: UUID, user_id: UUID, state: str) -> str:
        if not self.is_configured():
            raise AdsConfigurationMissingError(
                "Meta Ads",
                "META_ADS_APP_ID, META_ADS_APP_SECRET ou META_ADS_REDIRECT_URI non configurés."
            )
        params = {
            "client_id": self.app_id,
            "redirect_uri": self.redirect_uri,
            "state": state,
            "scope": ",".join(self.DEFAULT_SCOPES),
            "response_type": "code",
        }
        return f"{self.OAUTH_AUTH_ENDPOINT}?{urllib.parse.urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str | None = None) -> dict[str, Any]:
        if not self.is_configured():
            raise AdsConfigurationMissingError("Meta Ads")

        target_redirect = redirect_uri or self.redirect_uri
        params = {
            "client_id": self.app_id,
            "client_secret": self.app_secret,
            "redirect_uri": target_redirect,
            "code": code,
        }
        url = f"{self.OAUTH_TOKEN_ENDPOINT}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, method="GET")

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                err_body = json.loads(exc.read().decode("utf-8"))
                err_msg = err_body.get("error", {}).get("message") or str(exc)
            except Exception:
                err_msg = str(exc)
            raise AdsConnectorError(f"Échec échange code Meta Ads: {err_msg}", code="META_ADS_EXCHANGE_FAILED")
        except Exception as exc:
            raise AdsConnectorError(f"Erreur réseau Meta Ads: {exc}", code="META_ADS_NETWORK_ERROR")

        short_lived_token = data.get("access_token")

        # Échange contre un jeton longue durée (60 jours)
        long_lived_token = await self._exchange_long_lived_token(short_lived_token)

        return {
            "access_token": long_lived_token or short_lived_token,
            "token_type": data.get("token_type", "bearer"),
            "expires_in": 5184000 if long_lived_token else data.get("expires_in", 3600),
            "scope": ",".join(self.DEFAULT_SCOPES),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    async def _exchange_long_lived_token(self, short_token: str) -> str | None:
        try:
            params = {
                "grant_type": "fb_exchange_token",
                "client_id": self.app_id,
                "client_secret": self.app_secret,
                "fb_exchange_token": short_token,
            }
            url = f"{self.OAUTH_TOKEN_ENDPOINT}?{urllib.parse.urlencode(params)}"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("access_token")
        except Exception:
            return None

    async def refresh_token(self, credentials: dict[str, Any]) -> dict[str, Any]:
        # Meta refresh relies on token exchange
        tok = credentials.get("access_token")
        if not tok:
            raise AdsConnectorError("Aucun token Meta disponible", code="NO_META_TOKEN")
        new_tok = await self._exchange_long_lived_token(tok)
        updated = dict(credentials)
        if new_tok:
            updated["access_token"] = new_tok
            updated["updated_at"] = datetime.now(timezone.utc).isoformat()
        return updated

    async def list_campaigns(self, credentials: dict[str, Any], account_id: str | None = None) -> list[AdCampaign]:
        ad_account = account_id or credentials.get("ad_account_id")
        if not ad_account:
            return []

        if not ad_account.startswith("act_"):
            ad_account = f"act_{ad_account}"

        access_token = credentials.get("access_token")
        fields = "id,name,status,daily_budget,lifetime_budget,insights{spend,impressions,clicks,conversions,purchase_roas}"
        url = f"{self.GRAPH_API_BASE}/{ad_account}/campaigns?fields={fields}&access_token={access_token}&limit=50"

        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise AdsConnectorError(f"Erreur API Meta Ads ({exc.code}): {exc.reason}", code="META_ADS_API_ERROR")
        except Exception as exc:
            raise AdsConnectorError(f"Erreur réseau Meta Ads: {exc}", code="META_ADS_NETWORK_ERROR")

        campaigns: list[AdCampaign] = []
        for item in data.get("data", []):
            insights = item.get("insights", {}).get("data", [{}])[0] if item.get("insights", {}).get("data") else {}

            spend = Decimal(str(insights.get("spend", "0.00")))
            daily_budget_raw = item.get("daily_budget")
            daily_budget = (Decimal(str(daily_budget_raw)) / 100) if daily_budget_raw else None
            lifetime_budget_raw = item.get("lifetime_budget")
            lifetime_budget = (Decimal(str(lifetime_budget_raw)) / 100) if lifetime_budget_raw else None

            impressions = int(insights.get("impressions", 0))
            clicks = int(insights.get("clicks", 0))

            conversions = 0
            if "conversions" in insights and isinstance(insights["conversions"], list):
                conversions = sum(int(c.get("value", 0)) for c in insights["conversions"])

            ctr = (clicks / impressions * 100) if impressions > 0 else 0.0
            cpc = (spend / Decimal(clicks)) if clicks > 0 else Decimal("0.00")

            roas = 0.0
            roas_data = insights.get("purchase_roas", [])
            if roas_data and isinstance(roas_data, list):
                roas = float(roas_data[0].get("value", 0.0))

            campaigns.append(AdCampaign(
                id=str(item.get("id", "")),
                name=item.get("name", "Campagne Meta Ads"),
                status=item.get("status", "UNKNOWN"),
                provider="meta_ads",
                daily_budget_cad=daily_budget,
                lifetime_budget_cad=lifetime_budget,
                spend_cad=spend.quantize(Decimal("0.01")),
                impressions=impressions,
                clicks=clicks,
                conversions=conversions,
                ctr=round(ctr, 2),
                cpc_cad=cpc.quantize(Decimal("0.01")),
                roas=roas,
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
        active_count = sum(1 for c in campaigns if c.status == "ACTIVE")

        return AdsPerformanceSummary(
            provider="meta_ads",
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

