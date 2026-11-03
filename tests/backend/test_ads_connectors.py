"""Comprehensive test suite for Google Ads and Meta Ads connectors and API service."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from decimal import Decimal
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
)
from backend.app.connectors.ads.google_ads import GoogleAdsConnector
from backend.app.connectors.ads.meta_ads import MetaAdsConnector
from backend.app.dependencies.commerce import ConnectorSecretCipher
from backend.app.models.base import Base
from backend.app.models.commerce_connection import CommerceConnection, CommerceConnectionStatus
from backend.app.models.company import Company
from backend.app.models.user import User, UserRole
from backend.app.services.ads_service import AdsService


class DummyCipher:
    def encrypt(self, data: dict) -> str:
        return f"enc_{base64.b64encode(json.dumps(data).encode()).decode()}"

    def decrypt(self, token: str) -> dict:
        if token.startswith("enc_"):
            return json.loads(base64.b64decode(token[4:].encode()).decode())
        return json.loads(token)


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
        auth_jwt_secret="01234567890123456789012345678901",
        google_ads_client_id="test-google-client-id.apps.googleusercontent.com",
        google_ads_client_secret="test-google-client-secret",
        google_ads_developer_token="test-developer-token-1234",
        google_ads_redirect_uri="https://api.avenqo.ca/api/v1/ads/google/callback",
        meta_ads_app_id="123456789012345",
        meta_ads_app_secret="test-meta-app-secret-67890",
        meta_ads_redirect_uri="https://api.avenqo.ca/api/v1/ads/meta/callback",
    )


def test_google_ads_connector_unconfigured_raises_missing_config():
    connector = GoogleAdsConnector()
    assert not connector.is_configured()
    assert not connector.is_api_ready()
    with pytest.raises(AdsConfigurationMissingError, match="GOOGLE_ADS_CLIENT_ID"):
        connector.get_auth_url(uuid4(), uuid4(), "state123")


def test_google_ads_connector_auth_url_construction(dummy_settings):
    connector = GoogleAdsConnector(
        client_id=dummy_settings.google_ads_client_id,
        client_secret=dummy_settings.google_ads_client_secret,
        developer_token=dummy_settings.google_ads_developer_token,
        redirect_uri=dummy_settings.google_ads_redirect_uri,
    )
    assert connector.is_configured()
    assert connector.is_api_ready()

    url = connector.get_auth_url(uuid4(), uuid4(), "signed-state-xyz")
    assert "https://accounts.google.com/o/oauth2/v2/auth" in url
    assert f"client_id={dummy_settings.google_ads_client_id}" in url
    assert "access_type=offline" in url
    assert "state=signed-state-xyz" in url
    assert "adwords" in url


@pytest.mark.asyncio
async def test_google_ads_connector_list_campaigns_parses_gaql_response(dummy_settings):
    connector = GoogleAdsConnector(
        client_id=dummy_settings.google_ads_client_id,
        client_secret=dummy_settings.google_ads_client_secret,
        developer_token=dummy_settings.google_ads_developer_token,
        redirect_uri=dummy_settings.google_ads_redirect_uri,
    )

    fake_gaql_response = {
        "results": [
            {
                "campaign": {"id": "11223344", "name": "Campagne Recherche Printemps", "status": "ENABLED"},
                "metrics": {"costMicros": "150000000", "impressions": "5000", "clicks": "250", "conversions": 15},
                "campaignBudget": {"amountMicros": "25000000"},
            },
            {
                "campaign": {"id": "55667788", "name": "Remarketing Display", "status": "PAUSED"},
                "metrics": {"costMicros": "50000000", "impressions": "2000", "clicks": "80", "conversions": 4},
                "campaignBudget": {"amountMicros": "10000000"},
            },
        ]
    }

    class MockResp:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self):
            return json.dumps(fake_gaql_response).encode("utf-8")

    with patch("urllib.request.urlopen", return_value=MockResp()):
        campaigns = await connector.list_campaigns({"access_token": "tok123"}, account_id="123-456-7890")
        perf = await connector.get_performance({"access_token": "tok123"}, account_id="123-456-7890")

    assert len(campaigns) == 2
    c1 = campaigns[0]
    assert c1.id == "11223344"
    assert c1.name == "Campagne Recherche Printemps"
    assert c1.status == "ENABLED"
    assert c1.spend_cad == Decimal("150.00")
    assert c1.daily_budget_cad == Decimal("25.00")
    assert c1.impressions == 5000
    assert c1.clicks == 250
    assert c1.conversions == 15
    assert c1.ctr == 5.0
    assert c1.cpc_cad == Decimal("0.60")

    assert perf.total_spend_cad == Decimal("200.00")
    assert perf.total_impressions == 7000
    assert perf.total_clicks == 330
    assert perf.total_conversions == 19
    assert perf.campaigns_count == 2
    assert perf.active_campaigns_count == 1


def test_meta_ads_connector_unconfigured_raises():
    connector = MetaAdsConnector()
    assert not connector.is_configured()
    with pytest.raises(AdsConfigurationMissingError, match="META_ADS_APP_ID"):
        connector.get_auth_url(uuid4(), uuid4(), "state123")


def test_meta_ads_connector_auth_url_construction(dummy_settings):
    connector = MetaAdsConnector(
        app_id=dummy_settings.meta_ads_app_id,
        app_secret=dummy_settings.meta_ads_app_secret,
        redirect_uri=dummy_settings.meta_ads_redirect_uri,
    )
    assert connector.is_configured()
    url = connector.get_auth_url(uuid4(), uuid4(), "state_meta_456")
    assert "https://www.facebook.com/v20.0/dialog/oauth" in url
    assert f"client_id={dummy_settings.meta_ads_app_id}" in url
    assert "ads_read" in url
    assert "read_insights" in url


@pytest.mark.asyncio
async def test_meta_ads_connector_list_campaigns_and_performance(dummy_settings):
    connector = MetaAdsConnector(
        app_id=dummy_settings.meta_ads_app_id,
        app_secret=dummy_settings.meta_ads_app_secret,
        redirect_uri=dummy_settings.meta_ads_redirect_uri,
    )

    fake_meta_response = {
        "data": [
            {
                "id": "act_camp_9988",
                "name": "Instagram Stories Promo",
                "status": "ACTIVE",
                "daily_budget": 3000,  # 30.00 CAD
                "insights": {
                    "data": [
                        {
                            "spend": "120.50",
                            "impressions": "8500",
                            "clicks": "340",
                            "conversions": [{"action_type": "purchase", "value": "12"}],
                            "purchase_roas": [{"value": "3.85"}],
                        }
                    ]
                },
            }
        ]
    }

    class MockResp:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self):
            return json.dumps(fake_meta_response).encode("utf-8")

    with patch("urllib.request.urlopen", return_value=MockResp()):
        campaigns = await connector.list_campaigns({"access_token": "meta_tok"}, account_id="act_11223344")

    assert len(campaigns) == 1
    c = campaigns[0]
    assert c.id == "act_camp_9988"
    assert c.name == "Instagram Stories Promo"
    assert c.status == "ACTIVE"
    assert c.daily_budget_cad == Decimal("30.00")
    assert c.spend_cad == Decimal("120.50")
    assert c.impressions == 8500
    assert c.clicks == 340
    assert c.conversions == 12
    assert c.roas == 3.85


def test_ads_service_oauth_state_signature_and_tampering(dummy_settings, db_session):
    service = AdsService(db_session, dummy_settings, DummyCipher())
    co_id = uuid4()
    u_id = uuid4()

    state = service.generate_oauth_state(co_id, u_id, "google_ads")
    verified_co, verified_u = service.verify_oauth_state(state, "google_ads")
    assert verified_co == co_id
    assert verified_u == u_id

    # Tampered state rejection
    with pytest.raises(AdsConnectorError, match="altérée"):
        service.verify_oauth_state(f"{state}tampered", "google_ads")

    # Mismatched provider rejection
    with pytest.raises(AdsConnectorError, match="inattendu"):
        service.verify_oauth_state(state, "meta_ads")


@pytest.mark.asyncio
async def test_ads_service_connect_disconnect_and_isolation(dummy_settings, db_session):
    service = AdsService(db_session, dummy_settings, DummyCipher())
    tenant_a = uuid4()
    tenant_b = uuid4()

    with patch.object(service.google_ads, "exchange_code", return_value={"access_token": "a_tok", "customer_id": "111-222"}):
        conn_a = await service.connect_google_ads(tenant_a, "code_a")

    assert conn_a.company_id == tenant_a
    assert conn_a.provider == "google_ads"
    assert conn_a.status == CommerceConnectionStatus.CONNECTED.value
    assert conn_a.encrypted_credentials.startswith("enc_")

    # Verify tenant B cannot see tenant A's connection
    statuses_b = service.get_status(tenant_b)
    assert statuses_b["google_ads"].connected is False
    assert statuses_b["google_ads"].external_account_id is None

    # Status of tenant A
    statuses_a = service.get_status(tenant_a)
    assert statuses_a["google_ads"].connected is True
    assert statuses_a["google_ads"].external_account_id == "111-222"

    # Disconnect tenant A
    assert service.disconnect(tenant_a, "google_ads") is True
    conn_after = service.get_connection(tenant_a, "google_ads")
    assert conn_after.status == CommerceConnectionStatus.DISCONNECTED.value
    assert conn_after.encrypted_credentials is None


@pytest.mark.asyncio
async def test_ads_service_combined_performance(dummy_settings, db_session):
    service = AdsService(db_session, dummy_settings, DummyCipher())
    company_id = uuid4()

    # Create active mock connections
    conn_g = CommerceConnection(
        company_id=company_id,
        provider="google_ads",
        external_account_id="g_acc_1",
        status=CommerceConnectionStatus.CONNECTED.value,
        encrypted_credentials=DummyCipher().encrypt({"access_token": "gtok"}),
    )
    conn_m = CommerceConnection(
        company_id=company_id,
        provider="meta_ads",
        external_account_id="act_m_acc_2",
        status=CommerceConnectionStatus.CONNECTED.value,
        encrypted_credentials=DummyCipher().encrypt({"access_token": "mtok"}),
    )
    db_session.add_all([conn_g, conn_m])
    db_session.commit()

    camp_g = AdCampaign(
        id="g1", name="Camp G", status="ENABLED", provider="google_ads",
        spend_cad=Decimal("100.00"), impressions=2000, clicks=100, conversions=5,
    )
    camp_m = AdCampaign(
        id="m1", name="Camp M", status="ACTIVE", provider="meta_ads",
        spend_cad=Decimal("50.00"), impressions=1000, clicks=50, conversions=2,
    )

    with patch.object(service.google_ads, "list_campaigns", return_value=[camp_g]), \
         patch.object(service.meta_ads, "list_campaigns", return_value=[camp_m]):
        summary = await service.get_combined_performance(company_id)

    assert summary["total_spend_cad"] == 150.0
    assert summary["total_impressions"] == 3000
    assert summary["total_clicks"] == 150
    assert summary["total_conversions"] == 7
    assert summary["campaigns_count"] == 2
    assert summary["active_campaigns_count"] == 2
    assert "google_ads" in summary["providers_connected"]
    assert "meta_ads" in summary["providers_connected"]
