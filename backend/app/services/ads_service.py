"""Multi-tenant advertising service orchestrating Google Ads and Meta Ads connections."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.config.settings import Settings, get_settings
from backend.app.connectors.ads.base import (
    AdCampaign,
    AdsConfigurationMissingError,
    AdsConnectionStatus,
    AdsConnectorError,
    AdsPerformanceSummary,
)
from backend.app.connectors.ads.google_ads import GoogleAdsConnector
from backend.app.connectors.ads.meta_ads import MetaAdsConnector
from backend.app.dependencies.commerce import ConnectorSecretCipher, get_connector_secret_cipher
from backend.app.models.commerce_connection import CommerceConnection, CommerceConnectionStatus


class AdsService:
    """Provides high-level ads connection management and analytics for tenants."""

    def __init__(self, db: Session, settings: Settings | None = None, cipher: ConnectorSecretCipher | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.cipher = cipher or get_connector_secret_cipher()

        self.google_ads = GoogleAdsConnector(
            client_id=self.settings.google_ads_client_id,
            client_secret=self.settings.google_ads_client_secret,
            developer_token=self.settings.google_ads_developer_token,
            redirect_uri=self.settings.google_ads_redirect_uri,
        )
        self.meta_ads = MetaAdsConnector(
            app_id=self.settings.meta_ads_app_id,
            app_secret=self.settings.meta_ads_app_secret,
            redirect_uri=self.settings.meta_ads_redirect_uri,
        )

    def generate_oauth_state(self, company_id: UUID, user_id: UUID, provider: str) -> str:
        payload = {
            "company_id": str(company_id),
            "user_id": str(user_id),
            "provider": provider,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")).decode("utf-8").rstrip("=")
        secret = self.settings.auth_jwt_secret.encode("utf-8")
        signature = hmac.new(secret, encoded.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"{encoded}.{signature}"

    def verify_oauth_state(self, state: str, expected_provider: str) -> tuple[UUID, UUID]:
        parts = state.split(".")
        if len(parts) != 2:
            raise AdsConnectorError("Format de state OAuth invalide.", code="INVALID_OAUTH_STATE", status_code=400)

        encoded, signature = parts
        secret = self.settings.auth_jwt_secret.encode("utf-8")
        expected_sig = hmac.new(secret, encoded.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            raise AdsConnectorError("Signature de state OAuth altérée.", code="TAMPERED_OAUTH_STATE", status_code=400)

        padding = 4 - (len(encoded) % 4)
        if padding != 4:
            encoded += "=" * padding

        data = json.loads(base64.urlsafe_b64decode(encoded.encode("utf-8")).decode("utf-8"))
        if data.get("provider") != expected_provider:
            raise AdsConnectorError(f"Fournisseur OAuth inattendu: {data.get('provider')}", code="INVALID_PROVIDER", status_code=400)

        return UUID(data["company_id"]), UUID(data["user_id"])

    def get_connection(self, company_id: UUID, provider: str) -> CommerceConnection | None:
        return (
            self.db.query(CommerceConnection)
            .filter(
                CommerceConnection.company_id == company_id,
                CommerceConnection.provider == provider,
            )
            .first()
        )

    def get_status(self, company_id: UUID) -> dict[str, AdsConnectionStatus]:
        google_conn = self.get_connection(company_id, "google_ads")
        meta_conn = self.get_connection(company_id, "meta_ads")

        google_ready = self.google_ads.is_configured()
        google_api_ready = self.google_ads.is_api_ready()
        meta_ready = self.meta_ads.is_configured()

        google_instructions = None
        if not google_ready:
            google_instructions = "Configurer GOOGLE_ADS_CLIENT_ID, GOOGLE_ADS_CLIENT_SECRET et GOOGLE_ADS_REDIRECT_URI sur Railway."
        elif not google_api_ready:
            google_instructions = "GOOGLE_ADS_DEVELOPER_TOKEN manquant pour l'accès API. Demande de jeton développeur requise sur Google Cloud."

        meta_instructions = None
        if not meta_ready:
            meta_instructions = "Configurer META_ADS_APP_ID, META_ADS_APP_SECRET et META_ADS_REDIRECT_URI sur Railway."

        return {
            "google_ads": AdsConnectionStatus(
                provider="google_ads",
                connected=bool(google_conn and google_conn.status == CommerceConnectionStatus.CONNECTED.value),
                configured=google_ready,
                external_account_id=google_conn.external_account_id if google_conn else None,
                account_name=google_conn.display_name if google_conn else None,
                status=google_conn.status if google_conn else "DISCONNECTED",
                granted_scopes=google_conn.granted_scopes if google_conn else [],
                last_successful_sync=google_conn.last_successful_sync if google_conn else None,
                error_message=google_conn.sync_error_message if google_conn else None,
                setup_instructions=google_instructions,
            ),
            "meta_ads": AdsConnectionStatus(
                provider="meta_ads",
                connected=bool(meta_conn and meta_conn.status == CommerceConnectionStatus.CONNECTED.value),
                configured=meta_ready,
                external_account_id=meta_conn.external_account_id if meta_conn else None,
                account_name=meta_conn.display_name if meta_conn else None,
                status=meta_conn.status if meta_conn else "DISCONNECTED",
                granted_scopes=meta_conn.granted_scopes if meta_conn else [],
                last_successful_sync=meta_conn.last_successful_sync if meta_conn else None,
                error_message=meta_conn.sync_error_message if meta_conn else None,
                setup_instructions=meta_instructions,
            ),
        }

    async def connect_google_ads(self, company_id: UUID, code: str, customer_id: str | None = None) -> CommerceConnection:
        tokens = await self.google_ads.exchange_code(code)
        account_id = customer_id or tokens.get("customer_id") or "pending_account_select"

        conn = self.get_connection(company_id, "google_ads")
        if not conn:
            conn = CommerceConnection(
                company_id=company_id,
                provider="google_ads",
                external_account_id=account_id,
                display_name=f"Google Ads ({account_id})",
                status=CommerceConnectionStatus.CONNECTED.value,
                encrypted_credentials=self.cipher.encrypt(tokens),
                granted_scopes=[self.google_ads.SCOPE],
                capabilities=["campaigns:read", "metrics:read"],
                last_successful_sync=datetime.now(timezone.utc),
            )
            self.db.add(conn)
        else:
            conn.status = CommerceConnectionStatus.CONNECTED.value
            conn.external_account_id = account_id
            conn.encrypted_credentials = self.cipher.encrypt(tokens)
            conn.granted_scopes = [self.google_ads.SCOPE]
            conn.sync_error_message = None
            conn.last_successful_sync = datetime.now(timezone.utc)

        self.db.commit()
        self.db.refresh(conn)
        return conn

    async def connect_meta_ads(self, company_id: UUID, code: str, ad_account_id: str | None = None) -> CommerceConnection:
        tokens = await self.meta_ads.exchange_code(code)
        account_id = ad_account_id or tokens.get("ad_account_id") or "act_pending_select"

        conn = self.get_connection(company_id, "meta_ads")
        if not conn:
            conn = CommerceConnection(
                company_id=company_id,
                provider="meta_ads",
                external_account_id=account_id,
                display_name=f"Meta Ads ({account_id})",
                status=CommerceConnectionStatus.CONNECTED.value,
                encrypted_credentials=self.cipher.encrypt(tokens),
                granted_scopes=self.meta_ads.DEFAULT_SCOPES,
                capabilities=["campaigns:read", "insights:read"],
                last_successful_sync=datetime.now(timezone.utc),
            )
            self.db.add(conn)
        else:
            conn.status = CommerceConnectionStatus.CONNECTED.value
            conn.external_account_id = account_id
            conn.encrypted_credentials = self.cipher.encrypt(tokens)
            conn.granted_scopes = self.meta_ads.DEFAULT_SCOPES
            conn.sync_error_message = None
            conn.last_successful_sync = datetime.now(timezone.utc)

        self.db.commit()
        self.db.refresh(conn)
        return conn

    def disconnect(self, company_id: UUID, provider: str) -> bool:
        conn = self.get_connection(company_id, provider)
        if not conn:
            return False
        conn.status = CommerceConnectionStatus.DISCONNECTED.value
        conn.encrypted_credentials = None
        self.db.commit()
        return True

    def get_credentials(self, company_id: UUID, provider: str) -> dict[str, Any] | None:
        conn = self.get_connection(company_id, provider)
        if not conn or not conn.encrypted_credentials or conn.status != CommerceConnectionStatus.CONNECTED.value:
            return None
        return self.cipher.decrypt(conn.encrypted_credentials)

    async def get_campaigns(self, company_id: UUID, provider: str) -> list[AdCampaign]:
        creds = self.get_credentials(company_id, provider)
        if not creds:
            return []
        conn = self.get_connection(company_id, provider)
        account_id = conn.external_account_id if conn else None

        if provider == "google_ads":
            return await self.google_ads.list_campaigns(creds, account_id)
        elif provider == "meta_ads":
            return await self.meta_ads.list_campaigns(creds, account_id)
        return []

    async def get_combined_performance(self, company_id: UUID, period: str = "last_30d") -> dict[str, Any]:
        google_creds = self.get_credentials(company_id, "google_ads")
        meta_creds = self.get_credentials(company_id, "meta_ads")

        google_conn = self.get_connection(company_id, "google_ads")
        meta_conn = self.get_connection(company_id, "meta_ads")

        summaries: list[AdsPerformanceSummary] = []
        all_campaigns: list[AdCampaign] = []

        if google_creds and self.google_ads.is_api_ready():
            try:
                g_perf = await self.google_ads.get_performance(google_creds, google_conn.external_account_id if google_conn else None, period)
                summaries.append(g_perf)
                g_camps = await self.google_ads.list_campaigns(google_creds, google_conn.external_account_id if google_conn else None)
                all_campaigns.extend(g_camps)
            except Exception as exc:
                if google_conn:
                    google_conn.sync_error_message = str(exc)
                    self.db.commit()

        if meta_creds and self.meta_ads.is_configured():
            try:
                m_perf = await self.meta_ads.get_performance(meta_creds, meta_conn.external_account_id if meta_conn else None, period)
                summaries.append(m_perf)
                m_camps = await self.meta_ads.list_campaigns(meta_creds, meta_conn.external_account_id if meta_conn else None)
                all_campaigns.extend(m_camps)
            except Exception as exc:
                if meta_conn:
                    meta_conn.sync_error_message = str(exc)
                    self.db.commit()

        total_spend = sum((s.total_spend_cad for s in summaries), Decimal("0.00"))
        total_impressions = sum(s.total_impressions for s in summaries)
        total_clicks = sum(s.total_clicks for s in summaries)
        total_conversions = sum(s.total_conversions for s in summaries)

        avg_ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0.0
        avg_cpc = (total_spend / Decimal(total_clicks)) if total_clicks > 0 else Decimal("0.00")

        return {
            "period": period,
            "currency": "CAD",
            "total_spend_cad": float(total_spend),
            "total_impressions": total_impressions,
            "total_clicks": total_clicks,
            "total_conversions": total_conversions,
            "average_ctr": round(avg_ctr, 2),
            "average_cpc_cad": float(avg_cpc.quantize(Decimal("0.01"))),
            "campaigns_count": len(all_campaigns),
            "active_campaigns_count": sum(1 for c in all_campaigns if c.status in ("ENABLED", "ACTIVE")),
            "providers_connected": [s.provider for s in summaries],
            "campaigns": [
                {
                    "id": c.id,
                    "name": c.name,
                    "status": c.status,
                    "provider": c.provider,
                    "daily_budget_cad": float(c.daily_budget_cad) if c.daily_budget_cad else None,
                    "spend_cad": float(c.spend_cad),
                    "impressions": c.impressions,
                    "clicks": c.clicks,
                    "conversions": c.conversions,
                    "ctr": c.ctr,
                    "cpc_cad": float(c.cpc_cad),
                    "roas": c.roas,
                }
                for c in all_campaigns
            ],
        }

