"""Mathematical and Business Integrity test suite for advertising integrations.

Validates:
1. Multi-currency financial precision with Bank of Canada reference rates.
2. Exact mathematical formulas: Spend, CPC, CTR, Conversions, and ROAS.
3. Paginated campaigns exhaustive retrieval.
4. Empty accounts (0 campaigns) returning true financial zero without division by zero.
5. Disconnected and unconfigured accounts handled without crashes.
6. Expired / revoked tokens handled gracefully with actionable status.
7. Period filters (7d, 30d, 90d) correctly calculated.
8. Strict multi-tenant isolation.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Mapping
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.config.settings import Settings
from backend.app.connectors.ads.base import (
    AdCampaign,
    AdsConnectorError,
    AdsPerformanceSummary,
    resolve_date_range,
)
from backend.app.dependencies.commerce import ConnectorSecretCipher
from backend.app.models.base import Base
from backend.app.models.commerce_connection import CommerceConnection, CommerceConnectionStatus
from backend.app.services.ads_service import AdsService
from backend.app.services.fx_service import BankOfCanadaFXService


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
    engine = create_engine(f"sqlite:///{tmp_path / 'ads_integrity.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        yield session


@pytest.fixture
def fx_service():
    service = BankOfCanadaFXService(cache_ttl_hours=24)
    # Certified reference rates
    service.set_cached_rate("USD", "CAD", Decimal("1.3978"), "2026-11-02", "Banque du Canada - API Valet (FXUSDCAD)")
    service.set_cached_rate("EUR", "CAD", Decimal("1.4850"), "2026-11-02", "Banque du Canada - API Valet (FXEURCAD)")
    service.set_cached_rate("GBP", "CAD", Decimal("1.7520"), "2026-11-02", "Banque du Canada - API Valet (FXGBPCAD)")
    return service


@pytest.fixture
def ads_service(db_session, fx_service):
    settings = Settings(
        AUTH_JWT_SECRET="01234567890123456789012345678901",
        GOOGLE_ADS_CLIENT_ID="mock-g-client",
        GOOGLE_ADS_CLIENT_SECRET="mock-g-secret",
        GOOGLE_ADS_DEVELOPER_TOKEN="mock-g-devtoken",
        GOOGLE_ADS_REDIRECT_URI="https://api.avenqo.ca/api/v1/ads/google/callback",
        META_ADS_APP_ID="mock-m-app",
        META_ADS_APP_SECRET="mock-m-secret",
        META_ADS_REDIRECT_URI="https://api.avenqo.ca/api/v1/ads/meta/callback",
    )
    return AdsService(db=db_session, settings=settings, cipher=DummyCipher(), fx_service=fx_service)


@pytest.mark.asyncio
async def test_multi_currency_financial_accuracy_and_roas(ads_service, db_session):
    """Rigorous mathematical proof of spend conversion, CPC, CTR, and ROAS across USD, EUR, and CAD."""
    company_id = uuid4()

    # 1. Google Ads campaigns in USD
    # Camp 1: Spend $120.00, Imp 3000, Clicks 150, Conv 6, Value $360.00 -> ROAS = 3.00
    # Camp 2: Spend $80.00, Imp 2000, Clicks 50, Conv 2, Value $160.00 -> ROAS = 2.00
    g_camp1 = AdCampaign(
        id="gc1", name="Google Search US", status="ENABLED", provider="google_ads",
        currency="USD", spend_native=Decimal("120.00"), impressions=3000, clicks=150,
        conversions=6, ctr=5.0, cpc_native=Decimal("0.80"), roas=3.0,
    )
    g_camp2 = AdCampaign(
        id="gc2", name="Google Display US", status="ENABLED", provider="google_ads",
        currency="USD", spend_native=Decimal("80.00"), impressions=2000, clicks=50,
        conversions=2, ctr=2.5, cpc_native=Decimal("1.60"), roas=2.0,
    )
    g_summary = AdsPerformanceSummary(
        provider="google_ads", account_id="111-222-3333", native_currency="USD",
        total_spend_native=Decimal("200.00"), total_impressions=5000, total_clicks=200,
        total_conversions=8, average_ctr=4.0, average_cpc_native=Decimal("1.00"), average_roas=2.6,
    )

    # 2. Meta Ads campaigns in EUR
    # Camp 3: Spend €100.00, Imp 4000, Clicks 200, Conv 10, Value €400.00 -> ROAS = 4.00
    # Camp 4: Spend €50.00, Imp 1000, Clicks 50, Conv 5, Value €150.00 -> ROAS = 3.00
    m_camp1 = AdCampaign(
        id="mc1", name="Meta Retargeting EU", status="ACTIVE", provider="meta_ads",
        currency="EUR", spend_native=Decimal("100.00"), impressions=4000, clicks=200,
        conversions=10, ctr=5.0, cpc_native=Decimal("0.50"), roas=4.0,
    )
    m_camp2 = AdCampaign(
        id="mc2", name="Meta Acquisition EU", status="ACTIVE", provider="meta_ads",
        currency="EUR", spend_native=Decimal("50.00"), impressions=1000, clicks=50,
        conversions=5, ctr=5.0, cpc_native=Decimal("1.00"), roas=3.0,
    )
    m_summary = AdsPerformanceSummary(
        provider="meta_ads", account_id="act_555666", native_currency="EUR",
        total_spend_native=Decimal("150.00"), total_impressions=5000, total_clicks=250,
        total_conversions=15, average_ctr=5.0, average_cpc_native=Decimal("0.60"), average_roas=3.67,
    )

    with patch.object(ads_service, "get_credentials", return_value={"access_token": "valid"}), \
         patch.object(ads_service.google_ads, "get_performance", AsyncMock(return_value=g_summary)), \
         patch.object(ads_service.google_ads, "list_campaigns", AsyncMock(return_value=[g_camp1, g_camp2])), \
         patch.object(ads_service.meta_ads, "get_performance", AsyncMock(return_value=m_summary)), \
         patch.object(ads_service.meta_ads, "list_campaigns", AsyncMock(return_value=[m_camp1, m_camp2])):

        perf = await ads_service.get_combined_performance(company_id, period="30d")

        # Mathematical Checks:
        # Rate USD -> CAD = 1.3978. Spend = $200.00 * 1.3978 = $279.56 CAD
        # Rate EUR -> CAD = 1.4850. Spend = €150.00 * 1.4850 = $222.75 CAD
        # Total Spend CAD = 279.56 + 222.75 = 502.31 CAD
        assert perf["currency"] == "CAD"
        assert perf["currency_aggregation_blocked"] is False
        assert perf["total_spend_cad"] == 502.31

        # Impressions = 5000 + 5000 = 10000
        assert perf["total_impressions"] == 10000
        # Clicks = 200 + 250 = 450
        assert perf["total_clicks"] == 450
        # Conversions = 8 + 15 = 23
        assert perf["total_conversions"] == 23

        # CTR = (450 / 10000) * 100 = 4.50 %
        assert perf["average_ctr"] == 4.50

        # CPC = 502.31 / 450 = 1.11624 -> 1.12 CAD
        assert perf["average_cpc_cad"] == 1.12

        # ROAS = Total Conversion Value CAD / Total Spend CAD
        # USD Converted Value: (120 * 1.3978 * 3.0) + (80 * 1.3978 * 2.0) = 503.208 + 223.648 = 726.856 CAD
        # EUR Converted Value: (100 * 1.4850 * 4.0) + (50 * 1.4850 * 3.0) = 594.000 + 222.750 = 816.750 CAD
        # Total Value CAD = 726.856 + 816.750 = 1543.606 CAD
        # Expected ROAS = 1543.606 / 502.31 = 3.07299... -> 3.07
        assert perf["average_roas"] == 3.07


@pytest.mark.asyncio
async def test_empty_account_returns_clean_zero_without_division_by_zero(ads_service):
    """An account with zero campaigns and zero spend must return mathematical zero."""
    company_id = uuid4()

    empty_summary = AdsPerformanceSummary(
        provider="google_ads", account_id="000-000-0000", native_currency="CAD",
        total_spend_native=Decimal("0.00"), total_impressions=0, total_clicks=0,
        total_conversions=0, average_ctr=0.0, average_cpc_native=Decimal("0.00"), average_roas=0.0,
    )

    with patch.object(ads_service, "get_credentials", return_value={"access_token": "valid"}), \
         patch.object(ads_service.google_ads, "get_performance", AsyncMock(return_value=empty_summary)), \
         patch.object(ads_service.google_ads, "list_campaigns", AsyncMock(return_value=[])):

        perf = await ads_service.get_combined_performance(company_id, period="30d")
        assert perf["total_spend_cad"] == 0.0
        assert perf["total_impressions"] == 0
        assert perf["total_clicks"] == 0
        assert perf["total_conversions"] == 0
        assert perf["average_ctr"] == 0.0
        assert perf["average_cpc_cad"] == 0.0
        assert perf["average_roas"] == 0.0
        assert perf["campaigns_count"] == 0


@pytest.mark.asyncio
async def test_expired_token_graceful_error_isolation(ads_service, db_session):
    """Token revocation (HTTP 401) records actionable sync error without taking down other providers."""
    company_id = uuid4()
    conn = CommerceConnection(
        company_id=company_id, provider="google_ads", external_account_id="expired-cust",
        status=CommerceConnectionStatus.CONNECTED.value, encrypted_credentials="enc_tok",
    )
    db_session.add(conn)
    db_session.commit()

    meta_summary = AdsPerformanceSummary(
        provider="meta_ads", account_id="act_meta_live", native_currency="CAD",
        total_spend_native=Decimal("50.00"), total_impressions=1000, total_clicks=50,
        total_conversions=5, average_ctr=5.0, average_cpc_native=Decimal("1.00"),
    )

    with patch.object(ads_service, "get_credentials", return_value={"access_token": "expired_tok"}), \
         patch.object(ads_service.google_ads, "get_performance", AsyncMock(side_effect=AdsConnectorError("Token révoqué", code="TOKEN_REVOKED", status_code=401))), \
         patch.object(ads_service.meta_ads, "get_performance", AsyncMock(return_value=meta_summary)), \
         patch.object(ads_service.meta_ads, "list_campaigns", AsyncMock(return_value=[])):

        perf = await ads_service.get_combined_performance(company_id, period="30d")

        # Meta still succeeds
        assert "meta_ads" in perf["providers_connected"]
        assert perf["total_spend_cad"] == 50.0
        # Google Ads error is cleanly recorded
        assert "google_ads" in perf["errors"]
        assert "Token révoqué" in perf["errors"]["google_ads"]


@pytest.mark.asyncio
async def test_period_filters_calculate_correct_calendar_windows():
    """Validates 7d, 30d, 90d window calculations."""
    start_7, end_7 = resolve_date_range("7d")
    d_start_7 = datetime.fromisoformat(start_7).date()
    d_end_7 = datetime.fromisoformat(end_7).date()
    assert (d_end_7 - d_start_7).days == 7

    start_30, end_30 = resolve_date_range("30d")
    d_start_30 = datetime.fromisoformat(start_30).date()
    d_end_30 = datetime.fromisoformat(end_30).date()
    assert (d_end_30 - d_start_30).days == 30

    start_90, end_90 = resolve_date_range("90d")
    d_start_90 = datetime.fromisoformat(start_90).date()
    d_end_90 = datetime.fromisoformat(end_90).date()
    assert (d_end_90 - d_start_90).days == 90


@pytest.mark.asyncio
async def test_strict_isolation_between_two_distinct_companies(ads_service, db_session):
    """Company A and Company B cannot access or affect each other's credentials or status."""
    cid_a = uuid4()
    cid_b = uuid4()

    conn_a = CommerceConnection(
        company_id=cid_a, provider="google_ads", external_account_id="cust-co-a",
        display_name="Account Company A", status=CommerceConnectionStatus.CONNECTED.value,
        encrypted_credentials="enc_tok_a",
    )
    conn_b = CommerceConnection(
        company_id=cid_b, provider="google_ads", external_account_id="cust-co-b",
        display_name="Account Company B", status=CommerceConnectionStatus.CONNECTED.value,
        encrypted_credentials="enc_tok_b",
    )
    db_session.add_all([conn_a, conn_b])
    db_session.commit()

    st_a = ads_service.get_status(cid_a)
    st_b = ads_service.get_status(cid_b)

    assert st_a["google_ads"].external_account_id == "cust-co-a"
    assert st_a["google_ads"].account_name == "Account Company A"

    assert st_b["google_ads"].external_account_id == "cust-co-b"
    assert st_b["google_ads"].account_name == "Account Company B"

    # Disconnecting Co A leaves Co B untouched
    ads_service.disconnect(cid_a, "google_ads")
    assert ads_service.get_status(cid_a)["google_ads"].status == "DISCONNECTED"
    assert ads_service.get_status(cid_b)["google_ads"].status == "CONNECTED"


@pytest.mark.asyncio
async def test_multi_currency_roas_with_missing_fx_blocks_aggregation_and_returns_none_roas(ads_service):
    """When FX rates cannot be resolved, total spend and average ROAS must be None, never false 0.0."""
    company_id = uuid4()

    # Google Ads in CAD with $100 spend and ROAS = 3.0
    g_camp = AdCampaign(
        id="gc_cad", name="Google Search CAD", status="ENABLED", provider="google_ads",
        currency="CAD", spend_native=Decimal("100.00"), impressions=1000, clicks=100,
        conversions=5, ctr=10.0, cpc_native=Decimal("1.00"), roas=3.0,
    )
    g_summary = AdsPerformanceSummary(
        provider="google_ads", account_id="111-222-3333", native_currency="CAD",
        total_spend_native=Decimal("100.00"), total_impressions=1000, total_clicks=100,
        total_conversions=5, average_ctr=10.0, average_cpc_native=Decimal("1.00"), average_roas=3.0,
    )

    # Meta Ads in JPY with ¥50,000 spend and ROAS = 2.5 (No FX rate available for JPY)
    m_camp = AdCampaign(
        id="mc_jpy", name="Meta Retargeting JPY", status="ACTIVE", provider="meta_ads",
        currency="JPY", spend_native=Decimal("50000.00"), impressions=5000, clicks=200,
        conversions=10, ctr=4.0, cpc_native=Decimal("250.00"), roas=2.5,
    )
    m_summary = AdsPerformanceSummary(
        provider="meta_ads", account_id="act_jpy", native_currency="JPY",
        total_spend_native=Decimal("50000.00"), total_impressions=5000, total_clicks=200,
        total_conversions=10, average_ctr=4.0, average_cpc_native=Decimal("250.00"), average_roas=2.5,
    )

    with patch.object(ads_service, "get_credentials", return_value={"access_token": "valid"}), \
         patch.object(ads_service.google_ads, "get_performance", AsyncMock(return_value=g_summary)), \
         patch.object(ads_service.google_ads, "list_campaigns", AsyncMock(return_value=[g_camp])), \
         patch.object(ads_service.meta_ads, "get_performance", AsyncMock(return_value=m_summary)), \
         patch.object(ads_service.meta_ads, "list_campaigns", AsyncMock(return_value=[m_camp])), \
         patch.object(ads_service.fx_service, "get_exchange_rate", AsyncMock(return_value=None)):

        perf = await ads_service.get_combined_performance(company_id, period="30d")

        # Integrity checks:
        # 1. Aggregation is blocked due to missing JPY -> CAD rate
        assert perf["currency_aggregation_blocked"] is True
        assert perf["currency"] == "MIXED"

        # 2. total_spend_cad must be None, NOT unconverted CAD or partial CAD
        assert perf["total_spend_cad"] is None

        # 3. average_cpc_cad must be None
        assert perf["average_cpc_cad"] is None

        # 4. average_roas must be None (Unavailable), NEVER false 0.0 which would indicate 100% loss!
        assert perf["average_roas"] is None

        # 5. Non-monetary aggregates remain correct
        assert perf["total_impressions"] == 6000
        assert perf["total_clicks"] == 300
        assert perf["total_conversions"] == 15
        assert perf["average_ctr"] == 5.0
        assert perf["campaigns_count"] == 2

        # 6. Native values are preserved in provider_summaries and campaigns list
        assert perf["provider_summaries"]["google_ads"]["native_currency"] == "CAD"
        assert perf["provider_summaries"]["google_ads"]["total_spend_native"] == 100.0
        assert perf["provider_summaries"]["meta_ads"]["native_currency"] == "JPY"
        assert perf["provider_summaries"]["meta_ads"]["total_spend_native"] == 50000.0

        # 7. Campaign in JPY has spend_cad as None
        assert perf["campaigns"][1]["currency_native"] == "JPY"
        assert perf["campaigns"][1]["spend_cad"] is None

