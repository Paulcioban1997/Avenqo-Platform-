"""Multi-tenant advertising service orchestrating Google Ads and Meta Ads connections."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta, timezone
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
    resolve_date_range,
)
from backend.app.connectors.ads.google_ads import GoogleAdsConnector
from backend.app.connectors.ads.meta_ads import MetaAdsConnector
from backend.app.dependencies.commerce import ConnectorSecretCipher, get_connector_secret_cipher
from backend.app.models.commerce_connection import (
    CommerceConnection,
    CommerceConnectionStatus,
    CommerceOAuthState,
)

logger = logging.getLogger("avenqo.ads.service")

# Reference daily foreign exchange rates (Bank of Canada reference)
# In production, this can also query an external central bank / BoC daily FX endpoint
DEFAULT_FX_RATES: dict[tuple[str, str], tuple[Decimal, str]] = {
    ("USD", "CAD"): (Decimal("1.3650"), "Banque du Canada - Cours de référence quotidien"),
    ("EUR", "CAD"): (Decimal("1.4850"), "Banque du Canada - Cours de référence quotidien"),
    ("GBP", "CAD"): (Decimal("1.7420"), "Banque du Canada - Cours de référence quotidien"),
    ("CAD", "CAD"): (Decimal("1.0000"), "Parité CAD"),
}


class AdsService:
    """Provides high-level ads connection management, security, and multi-currency analytics."""

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

    def _state_hash(self, state: str) -> str:
        return hashlib.sha256(state.encode("utf-8")).hexdigest()

    def generate_oauth_state(self, company_id: UUID, user_id: UUID, provider: str) -> str:
        """Generates a cryptographically signed, single-use anti-replay OAuth state."""
        created_at = datetime.now(timezone.utc)
        expires_at = created_at + timedelta(minutes=10)
        nonce = base64.urlsafe_b64encode(hashlib.sha256(f"{company_id}:{user_id}:{created_at.isoformat()}".encode()).digest()[:16]).decode().rstrip("=")

        payload = {
            "company_id": str(company_id),
            "user_id": str(user_id),
            "provider": provider,
            "nonce": nonce,
            "created_at": created_at.isoformat(),
        }
        encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")).decode("utf-8").rstrip("=")
        secret = self.settings.auth_jwt_secret.encode("utf-8")
        signature = hmac.new(secret, encoded.encode("utf-8"), hashlib.sha256).hexdigest()
        full_state = f"{encoded}.{signature}"

        # Persist single-use state in database to prevent replay attacks
        state_record = CommerceOAuthState(
            company_id=company_id,
            actor_user_id=user_id,
            provider=provider,
            external_account_id="pending",
            state_hash=self._state_hash(full_state),
            created_at=created_at,
            expires_at=expires_at,
            consumed_at=None,
        )
        self.db.add(state_record)
        self.db.commit()

        return full_state

    def verify_oauth_state(self, state: str, expected_provider: str) -> tuple[UUID, UUID]:
        """Validates HMAC signature, expiration, and ensures single-use consumption against replay attacks."""
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

        try:
            data = json.loads(base64.urlsafe_b64decode(encoded.encode("utf-8")).decode("utf-8"))
        except Exception:
            raise AdsConnectorError("Charge utile de state OAuth illisible.", code="INVALID_OAUTH_PAYLOAD", status_code=400)

        if data.get("provider") != expected_provider:
            raise AdsConnectorError(f"Fournisseur OAuth inattendu: {data.get('provider')}", code="INVALID_PROVIDER", status_code=400)

        # Replay Attack & Expiration check in database
        state_hash = self._state_hash(state)
        record = self.db.query(CommerceOAuthState).filter(CommerceOAuthState.state_hash == state_hash).first()
        now = datetime.now(timezone.utc)

        if not record:
            raise AdsConnectorError("Tentative OAuth inconnue ou non initiée par cette plateforme.", code="UNKNOWN_OAUTH_STATE", status_code=400)

        if record.consumed_at is not None:
            raise AdsConnectorError("Jeton de state OAuth déjà consommé (tentative de rejeu interceptée).", code="REPLAY_ATTACK_DETECTED", status_code=400)

        # Check expiration
        exp = record.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < now:
            raise AdsConnectorError("Le délai d'autorisation OAuth a expiré (validité 10 min).", code="EXPIRED_OAUTH_STATE", status_code=400)

        # Mark consumed immediately
        record.consumed_at = now
        self.db.commit()

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
            google_instructions = "Définir GOOGLE_ADS_CLIENT_ID, GOOGLE_ADS_CLIENT_SECRET et GOOGLE_ADS_REDIRECT_URI."
        elif not google_api_ready:
            google_instructions = "Définir GOOGLE_ADS_DEVELOPER_TOKEN pour activer l'API de rapport Google Ads."

        meta_instructions = None
        if not meta_ready:
            meta_instructions = "Définir META_ADS_APP_ID, META_ADS_APP_SECRET et META_ADS_REDIRECT_URI."

        return {
            "google_ads": AdsConnectionStatus(
                provider="google_ads",
                connected=bool(google_conn and google_conn.status == CommerceConnectionStatus.CONNECTED.value),
                configured=google_api_ready,
                external_account_id=google_conn.external_account_id if google_conn else None,
                account_name=google_conn.display_name if google_conn else None,
                status=google_conn.status if google_conn else ("BLOCKED" if not google_api_ready else "DISCONNECTED"),
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
                status=meta_conn.status if meta_conn else ("BLOCKED" if not meta_ready else "DISCONNECTED"),
                granted_scopes=meta_conn.granted_scopes if meta_conn else [],
                last_successful_sync=meta_conn.last_successful_sync if meta_conn else None,
                error_message=meta_conn.sync_error_message if meta_conn else None,
                setup_instructions=meta_instructions,
            ),
        }

    async def connect_google_ads(self, company_id: UUID, code: str, customer_id: str | None = None) -> CommerceConnection:
        tokens = await self.google_ads.exchange_code(code)

        # Verify access, permissions, and fetch real account currency & metadata
        verification = await self.google_ads.verify_access(tokens, customer_id)
        account_id = verification.get("customer_id") or customer_id or "pending_account_select"
        currency = verification.get("currency") or "CAD"
        name = verification.get("account_name") or f"Google Ads ({account_id})"

        tokens["currency"] = currency
        tokens["account_name"] = name
        tokens["customer_id"] = account_id

        conn = self.get_connection(company_id, "google_ads")
        if not conn:
            conn = CommerceConnection(
                company_id=company_id,
                provider="google_ads",
                external_account_id=account_id,
                display_name=name,
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
            conn.display_name = name
            conn.encrypted_credentials = self.cipher.encrypt(tokens)
            conn.granted_scopes = [self.google_ads.SCOPE]
            conn.sync_error_message = None
            conn.last_successful_sync = datetime.now(timezone.utc)

        self.db.commit()
        self.db.refresh(conn)
        return conn

    async def connect_meta_ads(self, company_id: UUID, code: str, ad_account_id: str | None = None) -> CommerceConnection:
        tokens = await self.meta_ads.exchange_code(code)

        # Verify permissions, accessible accounts, and fetch real account currency & active status
        verification = await self.meta_ads.verify_access(tokens, ad_account_id)
        account_id = verification.get("ad_account_id") or ad_account_id or "pending_account_select"
        currency = verification.get("currency") or "CAD"
        name = verification.get("account_name") or f"Meta Ads ({account_id})"

        tokens["currency"] = currency
        tokens["account_name"] = name
        tokens["ad_account_id"] = account_id

        conn = self.get_connection(company_id, "meta_ads")
        if not conn:
            conn = CommerceConnection(
                company_id=company_id,
                provider="meta_ads",
                external_account_id=account_id,
                display_name=name,
                status=CommerceConnectionStatus.CONNECTED.value,
                encrypted_credentials=self.cipher.encrypt(tokens),
                granted_scopes=self.meta_ads.DEFAULT_SCOPES,
                capabilities=["campaigns:read", "metrics:read"],
                last_successful_sync=datetime.now(timezone.utc),
            )
            self.db.add(conn)
        else:
            conn.status = CommerceConnectionStatus.CONNECTED.value
            conn.external_account_id = account_id
            conn.display_name = name
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
        try:
            return self.cipher.decrypt(conn.encrypted_credentials)
        except Exception:
            return None

    async def get_campaigns(self, company_id: UUID, provider: str, period: str = "last_30d") -> list[AdCampaign]:
        creds = self.get_credentials(company_id, provider)
        if not creds:
            return []
        conn = self.get_connection(company_id, provider)
        account_id = conn.external_account_id if conn else None

        if provider == "google_ads":
            return await self.google_ads.list_campaigns(creds, account_id, period)
        elif provider == "meta_ads":
            return await self.meta_ads.list_campaigns(creds, account_id, period)
        return []

    async def get_combined_performance(self, company_id: UUID, period: str = "last_30d") -> dict[str, Any]:
        """Consolidates ads performance across providers with explicit multi-currency resolution."""
        google_creds = self.get_credentials(company_id, "google_ads")
        meta_creds = self.get_credentials(company_id, "meta_ads")

        google_conn = self.get_connection(company_id, "google_ads")
        meta_conn = self.get_connection(company_id, "meta_ads")

        summaries: list[AdsPerformanceSummary] = []
        all_campaigns: list[AdCampaign] = []
        errors: dict[str, str] = {}
        target_currency = "CAD"
        today_iso = datetime.now(timezone.utc).date().isoformat()

        # 1. Fetch Google Ads performance if configured & active
        if google_creds and self.google_ads.is_api_ready():
            try:
                g_perf = await self.google_ads.get_performance(google_creds, google_conn.external_account_id if google_conn else None, period)
                summaries.append(g_perf)
                g_camps = await self.google_ads.list_campaigns(google_creds, google_conn.external_account_id if google_conn else None, period)
                all_campaigns.extend(g_camps)
                if google_conn and google_conn.sync_error_message:
                    google_conn.sync_error_message = None
                    self.db.commit()
            except Exception as exc:
                err_msg = str(exc)
                errors["google_ads"] = err_msg
                if google_conn:
                    google_conn.sync_error_message = err_msg
                    self.db.commit()

        # 2. Fetch Meta Ads performance if configured & active
        if meta_creds and self.meta_ads.is_configured():
            try:
                m_perf = await self.meta_ads.get_performance(meta_creds, meta_conn.external_account_id if meta_conn else None, period)
                summaries.append(m_perf)
                m_camps = await self.meta_ads.list_campaigns(meta_creds, meta_conn.external_account_id if meta_conn else None, period)
                all_campaigns.extend(m_camps)
                if meta_conn and meta_conn.sync_error_message:
                    meta_conn.sync_error_message = None
                    self.db.commit()
            except Exception as exc:
                err_msg = str(exc)
                errors["meta_ads"] = err_msg
                if meta_conn:
                    meta_conn.sync_error_message = err_msg
                    self.db.commit()

        # 3. Currency resolution & conversion
        rates_used: list[dict[str, Any]] = []
        can_aggregate = True
        total_spend_target = Decimal("0.00")

        for s in summaries:
            source_curr = s.native_currency.upper().strip()
            if source_curr == target_currency:
                s.reference_currency = target_currency
                s.exchange_rate = Decimal("1.0000")
                s.total_spend_converted = s.total_spend_native
                s.average_cpc_converted = s.average_cpc_native
                total_spend_target += s.total_spend_native
            else:
                fx = DEFAULT_FX_RATES.get((source_curr, target_currency))
                if fx:
                    rate, source_name = fx
                    s.reference_currency = target_currency
                    s.exchange_rate = rate
                    s.exchange_rate_source = source_name
                    s.exchange_rate_date = today_iso
                    s.total_spend_converted = (s.total_spend_native * rate).quantize(Decimal("0.01"))
                    s.average_cpc_converted = (s.average_cpc_native * rate).quantize(Decimal("0.01"))
                    total_spend_target += s.total_spend_converted
                    rates_used.append({
                        "from_currency": source_curr,
                        "to_currency": target_currency,
                        "rate": float(rate),
                        "source": source_name,
                        "date": today_iso,
                    })
                else:
                    # Incompatible currency without rate -> block mixed aggregation
                    can_aggregate = False

        # Apply campaign currency conversion
        for c in all_campaigns:
            source_curr = c.currency.upper().strip()
            if source_curr == target_currency:
                c.converted_currency = target_currency
                c.exchange_rate = Decimal("1.0000")
                c.spend_converted = c.spend_native
                c.daily_budget_converted = c.daily_budget_native
                c.cpc_converted = c.cpc_native
            else:
                fx = DEFAULT_FX_RATES.get((source_curr, target_currency))
                if fx:
                    rate, source_name = fx
                    c.converted_currency = target_currency
                    c.exchange_rate = rate
                    c.exchange_rate_source = source_name
                    c.exchange_rate_date = today_iso
                    c.spend_converted = (c.spend_native * rate).quantize(Decimal("0.01"))
                    c.daily_budget_converted = (c.daily_budget_native * rate).quantize(Decimal("0.01")) if c.daily_budget_native else None
                    c.cpc_converted = (c.cpc_native * rate).quantize(Decimal("0.01"))

        total_impressions = sum(s.total_impressions for s in summaries)
        total_clicks = sum(s.total_clicks for s in summaries)
        total_conversions = sum(s.total_conversions for s in summaries)

        avg_ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0.0
        avg_cpc = (total_spend_target / Decimal(total_clicks)) if total_clicks > 0 else Decimal("0.00")

        start_date, end_date = resolve_date_range(period)

        return {
            "period": period,
            "start_date": start_date,
            "end_date": end_date,
            "currency": target_currency if can_aggregate else "MIXED",
            "currency_aggregation_blocked": not can_aggregate,
            "total_spend_cad": float(total_spend_target) if can_aggregate else None,
            "total_impressions": total_impressions,
            "total_clicks": total_clicks,
            "total_conversions": total_conversions,
            "average_ctr": round(avg_ctr, 2),
            "average_cpc_cad": float(avg_cpc.quantize(Decimal("0.01"))) if can_aggregate else None,
            "exchange_rates_applied": rates_used,
            "campaigns_count": len(all_campaigns),
            "active_campaigns_count": sum(1 for c in all_campaigns if c.status in ("ENABLED", "ACTIVE")),
            "providers_connected": [s.provider for s in summaries],
            "provider_summaries": {
                s.provider: {
                    "account_id": s.account_id,
                    "native_currency": s.native_currency,
                    "total_spend_native": float(s.total_spend_native),
                    "total_spend_converted_cad": float(s.total_spend_converted) if s.total_spend_converted is not None else None,
                    "impressions": s.total_impressions,
                    "clicks": s.total_clicks,
                    "conversions": s.total_conversions,
                    "ctr": s.average_ctr,
                    "cpc_native": float(s.average_cpc_native),
                }
                for s in summaries
            },
            "errors": errors,
            "campaigns": [
                {
                    "id": c.id,
                    "name": c.name,
                    "status": c.status,
                    "provider": c.provider,
                    "currency_native": c.currency,
                    "daily_budget_native": float(c.daily_budget_native) if c.daily_budget_native else None,
                    "spend_native": float(c.spend_native),
                    "spend_cad": float(c.spend_cad) if c.converted_currency == "CAD" or c.currency == "CAD" else None,
                    "impressions": c.impressions,
                    "clicks": c.clicks,
                    "conversions": c.conversions,
                    "ctr": c.ctr,
                    "cpc_native": float(c.cpc_native),
                    "roas": c.roas,
                }
                for c in all_campaigns
            ],
        }
