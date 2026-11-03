"""Comprehensive test suite for Google Ads v26 and Meta Ads v26.0 connectors and API service."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.config.settings import Settings
from backend.app.connectors.ads.base import (
    AdCampaign,
    AdsConfigurationMissingError,
    AdsConnectorError,
    AdsPerformanceSummary,
    resolve_date_range,
)
from backend.app.connectors.ads.google_ads import GoogleAdsConnector, _redact_secrets as redact_google
from backend.app.connectors.ads.meta_ads import MetaAdsConnector, _redact_secrets as redact_meta
from backend.app.dependencies.commerce import ConnectorSecretCipher
from backend.app.models.base import Base
from backend.app.models.commerce_connection import (
    CommerceConnection,
    CommerceConnectionStatus,
    CommerceOAuthState,
)
from backend.app.models.company import Company
from backend.app.models.user import User, UserRole
from backend.app.services.ads_service import AdsService


class DummyCipher(ConnectorSecretCipher):
    def __init__(self) -> None:
        pass

    def encrypt(self, payload: Mapping[str, Any]) -> str:
        return f"enc_{base64.b64encode(json.dumps(dict(payload)).encode()).decode()}"

    def decrypt(self, encrypted_payload: str) -> dict[str, Any]:
        if encrypted_payload.startswith("enc_"):
            return json.loads(base64.b64decode(encrypted_payload[4:].encode()).decode())
        return json.loads(encrypted_payload)


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'ads_test.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        yield session


@pytest.fixture
def dummy_settings():
    return Settings(
        AUTH_JWT_SECRET="01234567890123456789012345678901",
        GOOGLE_ADS_CLIENT_ID="test-google-client-id.apps.googleusercontent.com",
        GOOGLE_ADS_CLIENT_SECRET="test-google-client-secret",
        GOOGLE_ADS_DEVELOPER_TOKEN="test-developer-token-1234",
        GOOGLE_ADS_REDIRECT_URI="https://api.avenqo.ca/api/v1/ads/google/callback",
        META_ADS_APP_ID="123456789012345",
        META_ADS_APP_SECRET="test-meta-app-secret-67890",
        META_ADS_REDIRECT_URI="https://api.avenqo.ca/api/v1/ads/meta/callback",
    )


def test_google_ads_connector_uses_v26_and_constructs_auth_url(dummy_settings):
    connector = GoogleAdsConnector(
        client_id=dummy_settings.google_ads_client_id,
        client_secret=dummy_settings.google_ads_client_secret,
        developer_token=dummy_settings.google_ads_developer_token,
        redirect_uri=dummy_settings.google_ads_redirect_uri,
    )
    assert connector.API_VERSION == "v26"
    assert "https://googleads.googleapis.com/v26" == connector.GOOGLE_ADS_API_BASE
    assert connector.is_configured()
    assert connector.is_api_ready()

    url = connector.get_auth_url(uuid4(), uuid4(), "signed-state-xyz")
    assert "https://accounts.google.com/o/oauth2/v2/auth" in url
    assert f"client_id={dummy_settings.google_ads_client_id}" in url
    assert "access_type=offline" in url
    assert "state=signed-state-xyz" in url


@pytest.mark.asyncio
async def test_google_ads_connector_verify_access_and_currency(dummy_settings):
    connector = GoogleAdsConnector(
        client_id=dummy_settings.google_ads_client_id,
        client_secret=dummy_settings.google_ads_client_secret,
        developer_token=dummy_settings.google_ads_developer_token,
        redirect_uri=dummy_settings.google_ads_redirect_uri,
    )

    # Mock 1: listAccessibleCustomers, Mock 2: search customer metadata
    with patch("urllib.request.urlopen") as mock_url:
        mock_resp1 = MagicMock()
        mock_resp1.read.return_value = json.dumps({"resourceNames": ["customers/1234567890"]}).encode()
        mock_resp1.__enter__.return_value = mock_resp1

        mock_resp2 = MagicMock()
        mock_resp2.read.return_value = json.dumps({
            "results": [{
                "customer": {
                    "id": "1234567890",
                    "descriptiveName": "Compte Principal Google Ads",
                    "currencyCode": "USD",
                    "timeZone": "America/New_York",
                    "status": "ENABLED",
                }
            }]
        }).encode()
        mock_resp2.__enter__.return_value = mock_resp2

        mock_url.side_effect = [mock_resp1, mock_resp2]

        result = await connector.verify_access({"access_token": "mock-token"}, "123-456-7890")
        assert result["verified"] is True
        assert result["customer_id"] == "1234567890"
        assert result["currency"] == "USD"
        assert result["account_name"] == "Compte Principal Google Ads"


@pytest.mark.asyncio
async def test_google_ads_connector_list_campaigns_parses_gaql_response(dummy_settings):
    connector = GoogleAdsConnector(
        client_id=dummy_settings.google_ads_client_id,
        client_secret=dummy_settings.google_ads_client_secret,
        developer_token=dummy_settings.google_ads_developer_token,
        redirect_uri=dummy_settings.google_ads_redirect_uri,
    )

    fake_response = {
        "results": [
            {
                "campaign": {"id": "1001", "name": "Campagne Recherche Automne", "status": "ENABLED"},
                "metrics": {
                    "costMicros": 125500000,
                    "impressions": 4500,
                    "clicks": 180,
                    "conversions": 12,
                    "conversionsValue": 650.0,
                },
                "campaignBudget": {"amountMicros": 20000000},
                "customer": {"currencyCode": "CAD"},
            }
        ]
    }

    with patch("urllib.request.urlopen") as mock_url:
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(fake_response).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_url.return_value = mock_resp

        campaigns = await connector.list_campaigns({"access_token": "tok123"}, "123-456-7890", period="7d")
        assert len(campaigns) == 1
        c = campaigns[0]
        assert c.id == "1001"
        assert c.name == "Campagne Recherche Automne"
        assert c.status == "ENABLED"
        assert c.provider == "google_ads"
        assert c.currency == "CAD"
        assert c.spend_native == Decimal("125.50")
        assert c.daily_budget_native == Decimal("20.00")
        assert c.impressions == 4500
        assert c.clicks == 180
        assert c.conversions == 12
        assert c.ctr == 4.0
        assert c.cpc_native == Decimal("0.70")
        assert c.roas == 5.18


def test_meta_ads_connector_uses_v26_and_auth_url(dummy_settings):
    connector = MetaAdsConnector(
        app_id=dummy_settings.meta_ads_app_id,
        app_secret=dummy_settings.meta_ads_app_secret,
        redirect_uri=dummy_settings.meta_ads_redirect_uri,
    )
    assert connector.GRAPH_API_VERSION == "v26.0"
    assert "https://graph.facebook.com/v26.0" == connector.GRAPH_API_BASE
    url = connector.get_auth_url(uuid4(), uuid4(), "meta-state-123")
    assert "v26.0/dialog/oauth" in url
    assert f"client_id={dummy_settings.meta_ads_app_id}" in url
    assert "ads_read" in url


@pytest.mark.asyncio
async def test_meta_ads_connector_verify_access_and_rejects_disabled_account(dummy_settings):
    connector = MetaAdsConnector(
        app_id=dummy_settings.meta_ads_app_id,
        app_secret=dummy_settings.meta_ads_app_secret,
        redirect_uri=dummy_settings.meta_ads_redirect_uri,
    )

    with patch("urllib.request.urlopen") as mock_url:
        # 1. Permissions check -> ads_read granted
        mock_perm = MagicMock()
        mock_perm.read.return_value = json.dumps({"data": [{"permission": "ads_read", "status": "granted"}]}).encode()
        mock_perm.__enter__.return_value = mock_perm

        # 2. Ad accounts check -> account is DISABLED (status=2)
        mock_acc = MagicMock()
        mock_acc.read.return_value = json.dumps({
            "data": [{
                "id": "act_998877",
                "name": "Boutique Facebook Ads",
                "account_id": "998877",
                "currency": "CAD",
                "account_status": 2,  # 2 = DISABLED
            }]
        }).encode()
        mock_acc.__enter__.return_value = mock_acc

        mock_url.side_effect = [mock_perm, mock_acc]

        with pytest.raises(AdsConnectorError) as exc_info:
            await connector.verify_access({"access_token": "token123"}, "act_998877")
        assert exc_info.value.code == "ACCOUNT_DISABLED"


@pytest.mark.asyncio
async def test_meta_ads_connector_uses_bearer_header_without_token_in_url(dummy_settings):
    connector = MetaAdsConnector(
        app_id=dummy_settings.meta_ads_app_id,
        app_secret=dummy_settings.meta_ads_app_secret,
        redirect_uri=dummy_settings.meta_ads_redirect_uri,
    )

    fake_response = {
        "data": [
            {
                "id": "23849182",
                "name": "Campagne Meta Retargeting",
                "status": "ACTIVE",
                "daily_budget": "5000",
                "insights": {
                    "data": [
                        {
                            "spend": "85.20",
                            "impressions": 3200,
                            "clicks": 95,
                            "ctr": "2.97",
                            "cpc": "0.90",
                            "actions": [{"action_type": "purchase", "value": 7}],
                        }
                    ]
                },
            }
        ]
    }

    with patch("urllib.request.urlopen") as mock_url:
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(fake_response).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_url.return_value = mock_resp

        campaigns = await connector.list_campaigns({"access_token": "secret_meta_token_xyz"}, "act_123456", period="30d")
        assert len(campaigns) == 1
        c = campaigns[0]
        assert c.name == "Campagne Meta Retargeting"
        assert c.spend_native == Decimal("85.20")
        assert c.conversions == 7

        # Crucial security verification: inspect Request made
        called_req = mock_url.call_args[0][0]
        assert "access_token" not in called_req.full_url
        assert called_req.headers["Authorization"] == "Bearer secret_meta_token_xyz"


def test_redact_secrets_filters_tokens():
    raw_str = "Error calling Meta Ads with Bearer EAAB123456789xyz and client_secret=very_secret_key"
    clean_str = redact_meta(raw_str)
    assert "EAAB123456789xyz" not in clean_str
    assert "very_secret_key" not in clean_str
    assert "Bearer [REDACTED]" in clean_str


@pytest.mark.asyncio
async def test_ads_service_oauth_anti_replay_and_single_use(db_session, dummy_settings):
    service = AdsService(db=db_session, settings=dummy_settings, cipher=DummyCipher())
    company_id = uuid4()
    user_id = uuid4()

    state = service.generate_oauth_state(company_id, user_id, "google_ads")
    assert state is not None

    # First verification consumes the state
    cid, uid = service.verify_oauth_state(state, "google_ads")
    assert cid == company_id
    assert uid == user_id

    # Second verification MUST be rejected as a replay attack
    with pytest.raises(AdsConnectorError) as exc_info:
        service.verify_oauth_state(state, "google_ads")
    assert exc_info.value.code == "REPLAY_ATTACK_DETECTED"


@pytest.mark.asyncio
async def test_ads_service_multi_currency_conversion_and_incompatible_blocking(db_session, dummy_settings):
    service = AdsService(db=db_session, settings=dummy_settings, cipher=DummyCipher())
    company_id = uuid4()

    # Case 1: Google Ads in USD ($100) + Meta Ads in CAD ($200)
    # Expected: USD converted to CAD via 1.3650 (Bank of Canada rate) -> $136.50 + $200.00 = $336.50 CAD
    service.fx_service.set_cached_rate(
        "USD", "CAD", Decimal("1.3650"), "2026-11-02", source="Banque du Canada - API Valet (FXUSDCAD)"
    )
    summary_google_usd = AdsPerformanceSummary(
        provider="google_ads",
        account_id="111-222-3333",
        native_currency="USD",
        total_spend_native=Decimal("100.00"),
        total_impressions=5000,
        total_clicks=200,
        total_conversions=10,
        average_ctr=4.0,
        average_cpc_native=Decimal("0.50"),
    )
    summary_meta_cad = AdsPerformanceSummary(
        provider="meta_ads",
        account_id="act_444555",
        native_currency="CAD",
        total_spend_native=Decimal("200.00"),
        total_impressions=8000,
        total_clicks=400,
        total_conversions=20,
        average_ctr=5.0,
        average_cpc_native=Decimal("0.50"),
    )

    with patch.object(service, "get_credentials") as mock_creds, \
         patch.object(service.google_ads, "get_performance", AsyncMock(return_value=summary_google_usd)), \
         patch.object(service.google_ads, "list_campaigns", AsyncMock(return_value=[])), \
         patch.object(service.meta_ads, "get_performance", AsyncMock(return_value=summary_meta_cad)), \
         patch.object(service.meta_ads, "list_campaigns", AsyncMock(return_value=[])):

        mock_creds.return_value = {"access_token": "valid-token"}

        result = await service.get_combined_performance(company_id, period="30d")
        assert result["currency"] == "CAD"
        assert result["currency_aggregation_blocked"] is False
        assert result["total_spend_cad"] == 336.50
        assert result["total_impressions"] == 13000
        assert result["total_clicks"] == 600
        assert result["total_conversions"] == 30
        assert len(result["exchange_rates_applied"]) == 1
        assert result["exchange_rates_applied"][0]["from_currency"] == "USD"
        assert result["exchange_rates_applied"][0]["rate"] == 1.365

    # Case 2: Incompatible currency without certified rate (e.g. JPY without BoC observation) -> blocks mixed addition
    summary_jpy = AdsPerformanceSummary(
        provider="google_ads",
        account_id="888-999-0000",
        native_currency="JPY",
        total_spend_native=Decimal("15000.00"),
        total_impressions=1000,
        total_clicks=50,
        total_conversions=2,
    )
    with patch.object(service, "get_credentials") as mock_creds, \
         patch.object(service.fx_service, "get_exchange_rate", AsyncMock(return_value=None)), \
         patch.object(service.google_ads, "get_performance", AsyncMock(return_value=summary_jpy)), \
         patch.object(service.google_ads, "list_campaigns", AsyncMock(return_value=[])), \
         patch.object(service.meta_ads, "get_performance", AsyncMock(return_value=summary_meta_cad)), \
         patch.object(service.meta_ads, "list_campaigns", AsyncMock(return_value=[])):

        mock_creds.return_value = {"access_token": "valid-token"}

        result = await service.get_combined_performance(company_id, period="30d")
        assert result["currency"] == "MIXED"
        assert result["currency_aggregation_blocked"] is True
        assert result["total_spend_cad"] is None  # Blocked from generating an invalid mixed dollar total


@pytest.mark.asyncio
async def test_connect_fails_closed_when_no_authorized_account(db_session, dummy_settings):
    service = AdsService(db=db_session, settings=dummy_settings, cipher=DummyCipher())
    company_id = uuid4()

    with patch.object(service.google_ads, "exchange_code", AsyncMock(return_value={"access_token": "g_tok"})), \
         patch.object(service.google_ads, "verify_access", AsyncMock(return_value={"customer_id": ""})), \
         pytest.raises(AdsConnectorError) as exc_info:
        await service.connect_google_ads(company_id, "mock_code")
    assert exc_info.value.code == "NO_AUTHORIZED_ACCOUNT"

    with patch.object(service.meta_ads, "exchange_code", AsyncMock(return_value={"access_token": "m_tok"})), \
         patch.object(service.meta_ads, "verify_access", AsyncMock(return_value={"ad_account_id": ""})), \
         pytest.raises(AdsConnectorError) as exc_info_meta:
        await service.connect_meta_ads(company_id, "mock_code")
    assert exc_info_meta.value.code == "NO_AUTHORIZED_ACCOUNT"
