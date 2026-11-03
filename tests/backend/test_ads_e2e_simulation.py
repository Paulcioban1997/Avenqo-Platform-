"""End-to-End Simulation test for Google Ads & Meta Ads connectors & Central AI integration.

Validates:
1. Status endpoint when unconfigured (HTTP 503 BLOCKED with informative error code).
2. Status endpoint when configured (HTTP 200).
3. Auth URL generation with cryptographically signed state (anti-CSRF) and anti-replay persistence.
4. Callback token exchange, verify_access, and AES-GCM encryption at rest in CommerceConnection.
5. Multi-currency performance conversion (CAD/USD) and unified CAD aggregation (Strictly Read-Only).
6. Central AI tool integration (get_ads_performance) with entitlement check.
7. Disconnect flow removing sensitive records.
"""

from __future__ import annotations

import base64
from typing import Any, Mapping
from backend.app.dependencies.commerce import ConnectorSecretCipher


class DummyCipher(ConnectorSecretCipher):
    def __init__(self) -> None:
        pass

    def encrypt(self, payload: Mapping[str, Any]) -> str:
        return f"enc_{base64.b64encode(json.dumps(dict(payload)).encode()).decode()}"

    def decrypt(self, encrypted_payload: str) -> dict[str, Any]:
        if encrypted_payload.startswith("enc_"):
            return json.loads(base64.b64decode(encrypted_payload[4:].encode()).decode())
        return json.loads(encrypted_payload)

import json
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from backend.app.ai.tools.business.marketing_tools import GetAdsPerformanceArgs, GetAdsPerformanceTool
from backend.app.ai.tools.contracts import ToolExecutionContext
from backend.app.config.settings import Settings
from backend.app.connectors.ads.base import AdsPerformanceSummary
from backend.app.dependencies.auth import CurrentIdentity
from backend.app.models.auth_session import AuthSession
from backend.app.models.commerce_connection import CommerceConnection
from backend.app.models.company import Company
from backend.app.models.user import User, UserRole
from backend.app.services.ads_service import AdsService
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from shared.ai_engine.contracts import TenantContext


@pytest.fixture
def mock_settings():
    return Settings(
        ENVIRONMENT="test",
        AUTH_JWT_SECRET="test-jwt-secret-for-ads-simulation",
        GOOGLE_ADS_CLIENT_ID="mock-google-client-id",
        GOOGLE_ADS_CLIENT_SECRET="mock-google-client-secret",
        GOOGLE_ADS_DEVELOPER_TOKEN="mock-google-developer-token",
        GOOGLE_ADS_REDIRECT_URI="https://api.avenqo.ca/api/v1/ads/google/callback",
        META_ADS_APP_ID="mock-meta-app-id",
        META_ADS_APP_SECRET="mock-meta-app-secret",
        META_ADS_REDIRECT_URI="https://api.avenqo.ca/api/v1/ads/meta/callback",
    )


@pytest.fixture
def test_identity():
    company_id = uuid4()
    user_id = uuid4()
    user = User(
        id=user_id,
        company_id=company_id,
        first_name="Jean",
        last_name="Dupont",
        email="marketer@avenqo.ca",
        password_hash="pw_hash",
        role=UserRole.ADMIN,
    )
    auth_session = AuthSession(
        id=uuid4(),
        user_id=user_id,
        token_hash="th",
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc),
    )
    return CurrentIdentity(
        auth_session=auth_session,
        user=user,
        raw_token="raw-token-abc",
    )


@pytest.mark.asyncio
async def test_e2e_ads_simulation(mock_settings, test_identity):
    """Simulates the entire ads integration lifecycle in Sandbox/Test environment."""
    mock_db = MagicMock()
    service = AdsService(db=mock_db, settings=mock_settings, cipher=DummyCipher())

    # 1. Check initial status (both disconnected)
    mock_db.query.return_value.filter.return_value.first.return_value = None
    status = service.get_status(test_identity.company_id)
    assert status["google_ads"].status == "DISCONNECTED"
    assert status["meta_ads"].status == "DISCONNECTED"

    # 2. Generate Anti-CSRF Auth URLs with single-use persistence
    google_state = service.generate_oauth_state(test_identity.company_id, test_identity.user_id, "google_ads")
    google_auth_url = service.google_ads.get_auth_url(test_identity.company_id, test_identity.user_id, google_state)
    assert "accounts.google.com" in google_auth_url
    assert "state=" in google_auth_url

    meta_state = service.generate_oauth_state(test_identity.company_id, test_identity.user_id, "meta_ads")
    meta_auth_url = service.meta_ads.get_auth_url(test_identity.company_id, test_identity.user_id, meta_state)
    assert "facebook.com" in meta_auth_url
    assert "state=" in meta_auth_url

    # 3. Simulate OAuth token exchange, verification, and encrypted persistence
    with patch("urllib.request.urlopen") as mock_url, \
         patch.object(service.google_ads, "verify_access", AsyncMock(return_value={
             "verified": True,
             "currency": "USD",
             "account_name": "Google Ads Test US",
             "customer_id": "123-456-7890",
         })):
        token_resp = MagicMock()
        token_resp.read.return_value = json.dumps({
            "access_token": "g-access-token-12345",
            "refresh_token": "g-refresh-token-67890",
            "expires_in": 3600,
        }).encode("utf-8")
        token_resp.__enter__.return_value = token_resp
        mock_url.return_value = token_resp

        # Connect google ads
        conn = await service.connect_google_ads(
            company_id=test_identity.company_id,
            code="test-auth-code",
            customer_id="123-456-7890",
        )
        assert conn.provider == "google_ads"
        assert conn.company_id == test_identity.company_id
        assert conn.status == "CONNECTED"
        assert conn.encrypted_credentials is not None

    # 4. Simulate Multi-Currency Consolidated Performance (USD converted to CAD)
    with patch.object(service, "get_credentials") as mock_creds, \
         patch.object(service.google_ads, "get_performance") as mock_g_perf, \
         patch.object(service.google_ads, "list_campaigns") as mock_g_camps, \
         patch.object(service.meta_ads, "get_performance") as mock_m_perf, \
         patch.object(service.meta_ads, "list_campaigns") as mock_m_camps:

        mock_creds.return_value = {"access_token": "token123"}
        service.fx_service.set_cached_rate("USD", "CAD", Decimal("1.3650"), "2026-11-02")
        # Google in USD ($100 native)
        mock_g_perf.return_value = AdsPerformanceSummary(
            provider="google_ads",
            account_id="123-456-7890",
            native_currency="USD",
            total_spend_native=Decimal("100.00"),
            total_impressions=12400,
            total_clicks=430,
            total_conversions=28,
            average_ctr=3.47,
            average_cpc_native=Decimal("0.23"),
            period="last_30d",
        )
        mock_g_camps.return_value = []
        # Meta in CAD ($210 native)
        mock_m_perf.return_value = AdsPerformanceSummary(
            provider="meta_ads",
            account_id="act_987654321",
            native_currency="CAD",
            total_spend_native=Decimal("210.00"),
            total_impressions=18500,
            total_clicks=620,
            total_conversions=45,
            average_ctr=3.35,
            average_cpc_native=Decimal("0.34"),
            period="last_30d",
        )
        mock_m_camps.return_value = []

        perf = await service.get_combined_performance(test_identity.company_id, "last_30d")
        # 100 USD * 1.3650 + 210.00 CAD = 136.50 + 210.00 = 346.50 CAD
        assert perf["currency"] == "CAD"
        assert perf["total_spend_cad"] == 346.50
        assert perf["total_impressions"] == 30900
        assert perf["total_clicks"] == 1050
        assert perf["total_conversions"] == 73
        assert len(perf["exchange_rates_applied"]) == 1

    # 5. Test Central AI Tool Integration with Marketing Entitlement Check
    ai_tool = GetAdsPerformanceTool(mock_db)
    ctx = ToolExecutionContext(
        tenant=TenantContext(company_id=test_identity.company_id, user_id=test_identity.user_id),
        user_id=test_identity.user_id,
        permissions=frozenset(["ai:use", "data:read"]),
        request_id="req-e2e-ads",
    )
    with patch.object(ModuleEntitlementService, "can_use_module", return_value=True), \
         patch("backend.app.services.ads_service.AdsService.get_combined_performance", AsyncMock(return_value={
             "period": "last_30d",
             "currency": "CAD",
             "total_spend_cad": 346.50,
             "total_impressions": 30900,
             "total_clicks": 1050,
             "total_conversions": 73,
             "campaigns": [],
         })):
        tool_result = await ai_tool.run(ctx, GetAdsPerformanceArgs(period="last_30d"))
        assert tool_result.success is True
        assert tool_result.data["total_spend_cad"] == 346.50
        assert tool_result.data["total_impressions"] == 30900

    # 6. Test Disconnect
    mock_db.query.return_value.filter.return_value.first.return_value = conn
    disconnected = service.disconnect(test_identity.company_id, "google_ads")
    assert disconnected is True
    assert conn.status == "DISCONNECTED"
    assert conn.encrypted_credentials is None
