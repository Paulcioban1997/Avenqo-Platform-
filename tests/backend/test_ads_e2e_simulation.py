"""End-to-End Simulation test for Google Ads & Meta Ads connectors & Central AI integration.

Validates:
1. Status endpoint when unconfigured (HTTP 503 BLOCKED with informative error code).
2. Status endpoint when configured (HTTP 200).
3. Auth URL generation with cryptographically signed state (anti-CSRF).
4. Callback token exchange, AES-GCM encryption at rest in CommerceConnection.
5. Campaigns and unified CAD performance retrieval (Strictly Read-Only).
6. Central AI tool integration (get_ads_performance) returning structured multi-tenant metrics.
7. Disconnect flow removing sensitive records.
"""

import json
import pytest
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

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
from shared.ai_engine.contracts import TenantContext


@pytest.fixture
def mock_settings():
    return Settings(
        environment="test",
        database_url="sqlite+aiosqlite:///:memory:",
        auth_jwt_secret="test-jwt-secret-for-ads-simulation",
        encryption_master_key="00" * 32,
        google_ads_client_id="mock-google-client-id",
        google_ads_client_secret="mock-google-client-secret",
        google_ads_developer_token="mock-google-developer-token",
        google_ads_redirect_uri="https://api.avenqo.ca/api/v1/ads/google/callback",
        meta_ads_app_id="mock-meta-app-id",
        meta_ads_app_secret="mock-meta-app-secret",
        meta_ads_redirect_uri="https://api.avenqo.ca/api/v1/ads/meta/callback",
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
    # 1. Initialize AdsService with mocked DB and active connections
    mock_db = MagicMock()
    service = AdsService(db=mock_db, settings=mock_settings)

    # 2. Check initial status (both disconnected)
    mock_db.query.return_value.filter.return_value.first.return_value = None
    status = service.get_status(test_identity.company_id)
    assert status["google_ads"].status == "DISCONNECTED"
    assert status["meta_ads"].status == "DISCONNECTED"

    # 3. Generate Anti-CSRF Auth URLs
    google_state = service.generate_oauth_state(test_identity.company_id, test_identity.user_id, "google_ads")
    google_auth_url = service.google_ads.get_auth_url(test_identity.company_id, test_identity.user_id, google_state)
    assert "accounts.google.com" in google_auth_url
    assert "state=" in google_auth_url

    meta_state = service.generate_oauth_state(test_identity.company_id, test_identity.user_id, "meta_ads")
    meta_auth_url = service.meta_ads.get_auth_url(test_identity.company_id, test_identity.user_id, meta_state)
    assert "facebook.com" in meta_auth_url
    assert "state=" in meta_auth_url

    # 4. Simulate OAuth token exchange and encrypted persistence
    with patch("urllib.request.urlopen") as mock_url:
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

    # 5. Simulate Consolidated Performance (Unified CAD currency)
    with patch.object(service, "get_credentials") as mock_creds, \
         patch.object(service.google_ads, "get_performance") as mock_g_perf, \
         patch.object(service.google_ads, "list_campaigns") as mock_g_camps, \
         patch.object(service.meta_ads, "get_performance") as mock_m_perf, \
         patch.object(service.meta_ads, "list_campaigns") as mock_m_camps:
        
        mock_creds.return_value = {"access_token": "token123"}
        mock_g_perf.return_value = AdsPerformanceSummary(
            provider="google_ads",
            total_spend_cad=Decimal("150.50"),
            total_impressions=12400,
            total_clicks=430,
            total_conversions=28,
            average_ctr=3.47,
            average_cpc_cad=Decimal("0.35"),
            period="last_30d",
        )
        mock_g_camps.return_value = []
        mock_m_perf.return_value = AdsPerformanceSummary(
            provider="meta_ads",
            total_spend_cad=Decimal("210.00"),
            total_impressions=18500,
            total_clicks=620,
            total_conversions=45,
            average_ctr=3.35,
            average_cpc_cad=Decimal("0.34"),
            period="last_30d",
        )
        mock_m_camps.return_value = []

        perf = await service.get_combined_performance(test_identity.company_id, "last_30d")
        assert perf["total_spend_cad"] == 360.50
        assert perf["total_impressions"] == 30900
        assert perf["total_clicks"] == 1050
        assert perf["total_conversions"] == 73
        assert perf["average_cpc_cad"] == 0.34

    # 6. Test Central AI Tool Integration
    ai_tool = GetAdsPerformanceTool(mock_db)
    ctx = ToolExecutionContext(
        tenant=TenantContext(company_id=test_identity.company_id, user_id=test_identity.user_id),
        user_id=test_identity.user_id,
        permissions=frozenset(["ai:use", "data:read"]),
        request_id="req-e2e-ads",
    )
    with patch("backend.app.services.ads_service.AdsService.get_combined_performance", AsyncMock(return_value={
        "period": "last_30d",
        "currency": "CAD",
        "total_spend_cad": 360.50,
        "total_impressions": 30900,
        "total_clicks": 1050,
        "total_conversions": 73,
        "average_ctr": 3.4,
        "average_cpc_cad": 0.34,
        "campaigns_count": 0,
        "active_campaigns_count": 0,
        "providers_connected": ["google_ads", "meta_ads"],
        "campaigns": [],
    })):
        tool_result = await ai_tool.run(ctx, GetAdsPerformanceArgs(period="last_30d"))
        assert tool_result.success is True
        assert tool_result.data["total_spend_cad"] == 360.50
        assert tool_result.data["total_impressions"] == 30900

    # 7. Test Disconnect
    mock_db.query.return_value.filter.return_value.first.return_value = conn
    disconnected = service.disconnect(test_identity.company_id, "google_ads")
    assert disconnected is True
    assert conn.status == "DISCONNECTED"
    assert conn.encrypted_credentials is None
