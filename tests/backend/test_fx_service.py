"""Tests for BankOfCanadaFXService covering certified rates, caching, staleness, and errors."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from backend.app.services.fx_service import BankOfCanadaFXService, FXRateRecord


@pytest.fixture
def fx_service():
    return BankOfCanadaFXService(cache_ttl_hours=1, max_staleness_days=7, timeout_seconds=2.0)


@pytest.mark.asyncio
async def test_cad_parity_returns_exact_one(fx_service):
    record = await fx_service.get_rate_to_cad("CAD")
    assert record is not None
    assert record.rate == Decimal("1.00000000")
    assert record.from_currency == "CAD"
    assert record.to_currency == "CAD"
    assert "Parité" in record.source


@pytest.mark.asyncio
async def test_usd_boc_rate_parsing_and_caching(fx_service):
    mock_payload = {
        "observations": [
            {"d": "2026-10-30", "FXUSDCAD": {"v": "1.3960"}},
            {"d": "2026-11-02", "FXUSDCAD": {"v": "1.3978"}},
        ]
    }
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = json.dumps(mock_payload).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        record = await fx_service.get_rate_to_cad("USD")
        assert record is not None
        assert record.rate == Decimal("1.3978")
        assert record.observation_date == "2026-11-02"
        assert record.from_currency == "USD"
        assert record.to_currency == "CAD"
        assert "FXUSDCAD" in record.source
        assert mock_urlopen.call_count == 1

        # Second call must hit memory cache, not urllib
        cached_record = await fx_service.get_rate_to_cad("USD")
        assert cached_record == record
        assert mock_urlopen.call_count == 1


@pytest.mark.asyncio
async def test_recent_cache_with_old_observation_date_is_rejected(fx_service):
    """Proves that a technical cache created 1 minute ago is rejected if observation_date is economically stale."""
    now = datetime.now(timezone.utc)
    twenty_days_ago = (now - timedelta(days=20)).date().isoformat()

    # Pre-populate cache with an old observation date
    fx_service.set_cached_rate(
        from_currency="USD",
        to_currency="CAD",
        rate=Decimal("1.3500"),
        observation_date=twenty_days_ago,
        ttl_hours=24,  # Technical TTL is active
    )

    # get_rate_to_cad MUST reject it because observation_date is economically stale
    with patch("urllib.request.urlopen", side_effect=Exception("Provider offline")):
        record = await fx_service.get_rate_to_cad("USD")
        assert record is None


@pytest.mark.asyncio
async def test_weekend_observation_remains_valid_within_window(fx_service):
    """Observations from Friday (3-4 days old) remain valid across the weekend."""
    now = datetime.now(timezone.utc)
    three_days_ago = (now - timedelta(days=3)).date().isoformat()

    fx_service.set_cached_rate(
        from_currency="EUR",
        to_currency="CAD",
        rate=Decimal("1.4850"),
        observation_date=three_days_ago,
        ttl_hours=72,
    )

    record = await fx_service.get_rate_to_cad("EUR")
    assert record is not None
    assert record.rate == Decimal("1.4850")
    assert record.observation_date == three_days_ago


@pytest.mark.asyncio
async def test_provider_outage_with_economically_stale_cache_fails_closed(fx_service):
    """During a provider outage, if the residual cache is older than 7 days, it MUST NOT be used."""
    import urllib.error
    now = datetime.now(timezone.utc)
    nine_days_ago = (now - timedelta(days=9)).date().isoformat()

    fx_service.set_cached_rate(
        from_currency="GBP",
        to_currency="CAD",
        rate=Decimal("1.7400"),
        observation_date=nine_days_ago,
        ttl_hours=1,
    )

    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Bank of Canada 503")):
        record = await fx_service.get_rate_to_cad("GBP")
        assert record is None


@pytest.mark.asyncio
async def test_provider_outage_with_fresh_cache_succeeds(fx_service):
    """During a temporary network outage, residual cache with an observation date 2 days old is accepted."""
    import urllib.error
    now = datetime.now(timezone.utc)
    two_days_ago = (now - timedelta(days=2)).date().isoformat()

    fx_service.set_cached_rate(
        from_currency="USD",
        to_currency="CAD",
        rate=Decimal("1.3950"),
        observation_date=two_days_ago,
        ttl_hours=1,  # Technical TTL lapsed, but economic age is fresh
    )

    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Network timeout")):
        record = await fx_service.get_rate_to_cad("USD")
        assert record is not None
        assert record.rate == Decimal("1.3950")
        assert record.observation_date == two_days_ago


@pytest.mark.asyncio
async def test_cross_rate_usd_to_eur_calculation(fx_service):
    # Set certified rates: USD -> 1.4000 CAD, EUR -> 1.5000 CAD
    # Rate(USD -> EUR) = 1.4000 / 1.5000 = 0.93333333 EUR per USD
    today_iso = datetime.now(timezone.utc).date().isoformat()
    fx_service.set_cached_rate("USD", "CAD", Decimal("1.40000000"), today_iso)
    fx_service.set_cached_rate("EUR", "CAD", Decimal("1.50000000"), today_iso)

    cross = await fx_service.get_exchange_rate("USD", "EUR")
    assert cross is not None
    expected = (Decimal("1.40000000") / Decimal("1.50000000")).quantize(Decimal("0.00000001"))
    assert cross.rate == expected
    assert cross.from_currency == "USD"
    assert cross.to_currency == "EUR"
    assert "Calcul croisé" in cross.source


@pytest.mark.asyncio
async def test_unsupported_currency_returns_none(fx_service):
    record = await fx_service.get_rate_to_cad("XYZ_UNKNOWN_COIN")
    assert record is None


@pytest.mark.asyncio
async def test_stale_rate_exceeding_max_staleness_rejected(fx_service):
    # Observation date older than 7 days
    old_date = (datetime.now(timezone.utc) - timedelta(days=15)).date().isoformat()
    mock_payload = {
        "observations": [
            {"d": old_date, "FXUSDCAD": {"v": "1.3500"}},
        ]
    }
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = json.dumps(mock_payload).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        record = await fx_service.get_rate_to_cad("USD")
        assert record is None


@pytest.mark.asyncio
async def test_empty_observations_fails_closed(fx_service):
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = json.dumps({"observations": []}).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        record = await fx_service.get_rate_to_cad("USD")
        assert record is None
