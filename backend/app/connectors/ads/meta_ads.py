"""Meta Ads (Facebook / Instagram) connector implementation using Meta Graph API v26.0."""

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

logger = logging.getLogger("avenqo.ads.meta")


def _redact_secrets(text: str) -> str:
    """Masks authorization tokens, client secrets, and sensitive credentials in logs/exceptions."""
    sanitized = re.sub(r"(Bearer\s+)[A-Za-z0-9._\-]+", r"\1[REDACTED]", text)
    sanitized = re.sub(r"(client_secret=)[^&]+", r"\1[REDACTED]", sanitized)
    sanitized = re.sub(r"(access_token=)[^&]+", r"\1[REDACTED]", sanitized)
    return sanitized


class MetaAdsConnector(BaseAdsConnector):
    """Integrates with Meta Marketing Graph API v26.0 in strict read-only mode."""

    GRAPH_API_VERSION = "v26.0"
    OAUTH_AUTH_ENDPOINT = f"https://www.facebook.com/{GRAPH_API_VERSION}/dialog/oauth"
    OAUTH_TOKEN_ENDPOINT = f"https://graph.facebook.com/{GRAPH_API_VERSION}/oauth/access_token"
    GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"
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
        body_data: dict[str, Any] = {
            "client_id": self.app_id,
            "client_secret": self.app_secret,
            "redirect_uri": target_redirect,
            "code": code,
        }
        payload = urllib.parse.urlencode(body_data).encode("utf-8")
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
                err_msg = err_body.get("error", {}).get("message") or str(exc)
            except Exception:
                err_msg = str(exc)
            raise AdsConnectorError(_redact_secrets(f"Échec échange code Meta Ads: {err_msg}"), code="META_ADS_EXCHANGE_FAILED")
        except Exception as exc:
            raise AdsConnectorError(_redact_secrets(f"Erreur réseau Meta Ads: {exc}"), code="META_ADS_NETWORK_ERROR")

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
            exchange_data: dict[str, Any] = {
                "grant_type": "fb_exchange_token",
                "client_id": self.app_id,
                "client_secret": self.app_secret,
                "fb_exchange_token": short_token,
            }
            payload = urllib.parse.urlencode(exchange_data).encode("utf-8")
            req = urllib.request.Request(
                self.OAUTH_TOKEN_ENDPOINT,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                return res.get("access_token")
        except Exception as exc:
            logger.warning("Échec obtention token longue durée Meta Ads: %s", _redact_secrets(str(exc)))
            return None

    async def refresh_token(self, credentials: dict[str, Any]) -> dict[str, Any]:
        """Meta Graph tokens can be refreshed before expiration using fb_exchange_token."""
        current_token = credentials.get("access_token")
        if not current_token:
            raise AdsConnectorError("Aucun access_token disponible pour Meta Ads.", code="NO_ACCESS_TOKEN")

        new_token = await self._exchange_long_lived_token(current_token)
        if not new_token:
            raise AdsConnectorError("Impossible de renouveler le token Meta Ads.", code="META_ADS_REFRESH_FAILED")

        updated = dict(credentials)
        updated["access_token"] = new_token
        updated["expires_in"] = 5184000
        updated["updated_at"] = datetime.now(timezone.utc).isoformat()
        return updated

    async def verify_access(self, credentials: dict[str, Any], account_id: str | None = None) -> dict[str, Any]:
        """Verifies ads_read permission, active account status (1), and fetches currency."""
        access_token = credentials.get("access_token")
        if not access_token:
            raise AdsConnectorError("Jeton d'accès Meta Ads manquant.", code="NO_ACCESS_TOKEN")

        headers = {"Authorization": f"Bearer {access_token}"}

        # 1. Verify permissions
        perm_url = f"{self.GRAPH_API_BASE}/me/permissions"
        req_perm = urllib.request.Request(perm_url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req_perm, timeout=15) as resp:
                perm_data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise AdsConnectorError("Jeton Meta Ads expiré ou révoqué.", code="TOKEN_REVOKED", status_code=401)
            raise AdsConnectorError(_redact_secrets(f"Erreur vérification permissions Meta Ads ({exc.code}): {exc.reason}"), code="META_ADS_API_ERROR")
        except Exception as exc:
            raise AdsConnectorError(_redact_secrets(f"Erreur réseau Meta Ads: {exc}"), code="META_ADS_NETWORK_ERROR")

        granted_perms = {p["permission"] for p in perm_data.get("data", []) if p.get("status") == "granted"}
        if "ads_read" not in granted_perms and "read_insights" not in granted_perms:
            raise AdsConnectorError(
                "L'autorisation Meta accordée ne contient pas les permissions requises ('ads_read' ou 'read_insights').",
                code="INSUFFICIENT_PERMISSIONS",
                status_code=403,
            )

        # 2. List accessible ad accounts
        accounts_url = f"{self.GRAPH_API_BASE}/me/adaccounts?fields=id,name,account_id,currency,account_status"
        req_acc = urllib.request.Request(accounts_url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req_acc, timeout=15) as resp:
                acc_data = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            raise AdsConnectorError(_redact_secrets(f"Erreur récupération comptes Meta Ads: {exc}"), code="META_ADS_API_ERROR")

        accessible_accounts = acc_data.get("data", [])
        if not accessible_accounts:
            return {
                "accessible_accounts": [],
                "verified": False,
                "currency": "CAD",
                "status": "NO_AD_ACCOUNTS",
            }

        target_id = (account_id or credentials.get("ad_account_id") or "").strip()
        selected = None
        if target_id:
            normalized_target = target_id if target_id.startswith("act_") else f"act_{target_id}"
            for acc in accessible_accounts:
                if acc.get("id") == normalized_target or acc.get("account_id") == target_id:
                    selected = acc
                    break
            if not selected:
                raise AdsConnectorError(
                    f"Le compte publicitaire Meta {target_id} n'appartient pas aux comptes accessibles par cet utilisateur.",
                    code="ACCOUNT_ACCESS_DENIED",
                    status_code=403,
                )
        else:
            selected = accessible_accounts[0]

        # 3. Check account status (1 = ACTIVE)
        account_status = selected.get("account_status", 1)
        if account_status != 1:
            status_desc = {2: "DISABLED", 3: "UNSETTLED", 7: "PENDING_RISK_REVIEW", 8: "PENDING_SETTLEMENT"}.get(account_status, f"CODE_{account_status}")
            raise AdsConnectorError(
                f"Le compte publicitaire Meta {selected.get('id')} n'est pas actif (statut={status_desc}).",
                code="ACCOUNT_DISABLED",
                status_code=400,
            )

        return {
            "verified": True,
            "ad_account_id": selected.get("id"),
            "account_name": selected.get("name") or selected.get("id"),
            "currency": selected.get("currency") or "CAD",
            "account_status": "ACTIVE",
            "accessible_accounts": [a.get("id") for a in accessible_accounts],
        }

    async def list_campaigns(
        self, credentials: dict[str, Any], account_id: str | None = None, period: str = "last_30d"
    ) -> list[AdCampaign]:
        ad_account_id = (account_id or credentials.get("ad_account_id") or "").strip()
        if not ad_account_id:
            return []

        if not ad_account_id.startswith("act_"):
            ad_account_id = f"act_{ad_account_id}"

        start_date, end_date = resolve_date_range(period)
        access_token = credentials.get("access_token")
        if not access_token:
            return []

        # Use Authorization header, NEVER query params
        headers = {"Authorization": f"Bearer {access_token}"}
        native_currency = credentials.get("currency") or "CAD"

        fields = (
            "id,name,status,daily_budget,lifetime_budget,"
            f"insights.time_range({{'since':'{start_date}','until':'{end_date}'}})"
            "{{spend,impressions,clicks,actions,cost_per_action_type,ctr,cpc}}"
        )
        url = f"{self.GRAPH_API_BASE}/{ad_account_id}/campaigns?fields={urllib.parse.quote(fields)}&limit=50"

        campaigns: list[AdCampaign] = []
        next_url: str | None = url
        max_pages = 5

        for _ in range(max_pages):
            if not next_url:
                break
            req = urllib.request.Request(next_url, headers=headers, method="GET")
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                if exc.code == 401:
                    raise AdsConnectorError("Jeton d'accès Meta Ads révoqué ou expiré.", code="TOKEN_REVOKED", status_code=401)
                raise AdsConnectorError(_redact_secrets(f"Erreur API Meta Ads ({exc.code}): {exc.reason}"), code="META_ADS_API_ERROR")
            except Exception as exc:
                raise AdsConnectorError(_redact_secrets(f"Erreur réseau Meta Ads: {exc}"), code="META_ADS_NETWORK_ERROR")

            for item in data.get("data", []):
                insights_data = item.get("insights", {}).get("data", [])
                insight = insights_data[0] if insights_data else {}

                spend = Decimal(str(insight.get("spend", "0.00")))
                daily_raw = item.get("daily_budget")
                daily_budget = (Decimal(daily_raw) / Decimal(100)) if daily_raw else None
                life_raw = item.get("lifetime_budget")
                lifetime_budget = (Decimal(life_raw) / Decimal(100)) if life_raw else None

                impressions = int(insight.get("impressions", 0))
                clicks = int(insight.get("clicks", 0))
                actions = insight.get("actions", [])
                conversions = 0
                for act in actions:
                    if act.get("action_type") in ("purchase", "omni_purchase", "lead", "complete_registration"):
                        conversions += int(act.get("value", 0))

                action_values = insight.get("action_values", [])
                conversion_value = Decimal("0.00")
                for av in action_values:
                    if av.get("action_type") in ("purchase", "omni_purchase"):
                        try:
                            conversion_value += Decimal(str(av.get("value", "0.00")))
                        except Exception:
                            pass
                roas = float(conversion_value / spend) if spend > Decimal("0.00") else 0.0

                ctr = float(insight.get("ctr", 0.0))
                cpc = Decimal(str(insight.get("cpc", "0.00"))) if clicks > 0 else Decimal("0.00")

                campaigns.append(AdCampaign(
                    id=str(item.get("id")),
                    name=item.get("name", "Campagne Meta Ads"),
                    status=item.get("status", "UNKNOWN"),
                    provider="meta_ads",
                    currency=native_currency,
                    daily_budget_native=daily_budget,
                    lifetime_budget_native=lifetime_budget,
                    spend_native=spend.quantize(Decimal("0.01")),
                    impressions=impressions,
                    clicks=clicks,
                    conversions=conversions,
                    ctr=round(ctr, 2),
                    cpc_native=cpc.quantize(Decimal("0.01")),
                    roas=round(roas, 2),
                ))

            # Pagination handling
            next_url = data.get("paging", {}).get("next")

        return campaigns

    async def get_performance(
        self, credentials: dict[str, Any], account_id: str | None = None, period: str = "last_30d"
    ) -> AdsPerformanceSummary:
        campaigns = await self.list_campaigns(credentials, account_id, period)
        start_date, end_date = resolve_date_range(period)
        act_id = (account_id or credentials.get("ad_account_id") or "").strip()
        native_currency = credentials.get("currency") or "CAD"

        if not campaigns:
            return AdsPerformanceSummary(
                provider="meta_ads",
                account_id=act_id,
                native_currency=native_currency,
                period=period,
                start_date=start_date,
                end_date=end_date,
            )

        total_spend = sum((c.spend_native for c in campaigns), Decimal("0.00"))
        total_impressions = sum(c.impressions for c in campaigns)
        total_clicks = sum(c.clicks for c in campaigns)
        total_conversions = sum(c.conversions for c in campaigns)
        avg_ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0.0
        avg_cpc = (total_spend / Decimal(total_clicks)) if total_clicks > 0 else Decimal("0.00")
        total_conv_value = sum(Decimal(str(c.roas)) * c.spend_native for c in campaigns)
        avg_roas = float(total_conv_value / total_spend) if total_spend > Decimal("0.00") else 0.0

        return AdsPerformanceSummary(
            provider="meta_ads",
            account_id=act_id,
            native_currency=native_currency,
            total_spend_native=total_spend.quantize(Decimal("0.01")),
            total_impressions=total_impressions,
            total_clicks=total_clicks,
            total_conversions=total_conversions,
            average_ctr=round(avg_ctr, 2),
            average_cpc_native=avg_cpc.quantize(Decimal("0.01")),
            average_roas=round(avg_roas, 2),
            campaigns_count=len(campaigns),
            active_campaigns_count=sum(1 for c in campaigns if c.status in ("ACTIVE", "ENABLED")),
            period=period,
            start_date=start_date,
            end_date=end_date,
        )
