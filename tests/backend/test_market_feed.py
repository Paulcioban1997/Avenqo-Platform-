import pytest

from backend.app.services.market_feed import (
    MarketUnavailable,
    asset_classes,
    classify_freshness,
    experimental_study,
    indicator_snapshot,
    resolve_quote,
    watch_symbol,
)
from backend.app.services.market_stream import parse_binance_message, parse_coinbase_message, reconnect_delay
from modules.registry import get_business_module


def test_trading_is_an_optional_module():
    trading = get_business_module("trading")
    assert trading is not None
    assert trading.included is False


def test_freshness_is_live_only_for_a_current_socket():
    now = 1_000_000
    assert classify_freshness("websocket", now - 5_000, now) == "live"
    assert classify_freshness("rest", now - 5_000, now) == "delayed"
    assert classify_freshness("websocket", now - 130_000, now) == "stale"
    assert classify_freshness("rest", 0, now) == "unavailable"


def test_fallback_uses_the_second_provider_and_never_invents_a_price():
    def down(_symbol: str) -> dict:
        raise MarketUnavailable("down")

    def coinbase(symbol: str) -> dict:
        return {"symbol": symbol, "price": 101.5, "updated_at": 5_000, "transport": "rest", "source": "coinbase-public"}

    row = resolve_quote("BTC-USDT", "auto", {"binance": down, "coinbase": coinbase}, 5_000)
    assert row["price"] == 101.5
    assert row["freshness"] == "delayed"
    with pytest.raises(MarketUnavailable):
        resolve_quote("BTC-USDT", "auto", {"binance": down, "coinbase": down}, 5_000)


def test_explicit_binance_does_not_silently_switch_to_coinbase():
    def coinbase(symbol: str) -> dict:
        return {"symbol": symbol, "price": 1, "updated_at": 5_000, "transport": "rest", "source": "coinbase-public"}

    with pytest.raises(MarketUnavailable):
        resolve_quote("BTC-USD", "binance", {"coinbase": coinbase}, 5_000)


def test_indicators_are_calculations_without_a_prediction():
    closes = [float(index) for index in range(1, 60)]
    snapshot = indicator_snapshot(closes)
    assert snapshot["sma_20"] == pytest.approx(49.5)
    assert snapshot["rsi_14"] == 100.0
    assert snapshot["prediction"] is None
    assert snapshot["bollinger"]["upper"] > snapshot["bollinger"]["middle"]
    study = experimental_study(closes)
    assert study["reliable"] is False
    assert study["advice"] is None
    assert study["estimate"] is None


def test_watch_symbol_rejects_links_and_keeps_usdt_compact():
    assert watch_symbol("btc-usdt") == "BTCUSDT"
    assert watch_symbol("ETH-USD") == "ETH-USD"
    with pytest.raises(ValueError):
        watch_symbol("https://evil.example")


def test_stream_parsers_use_exchange_numbers():
    row = parse_binance_message({"data": {
        "e": "24hrMiniTicker", "s": "BTCUSDT", "c": "62000", "o": "61000", "h": "63000", "l": "60000", "v": "12", "E": 1234,
    }})
    assert row is not None
    assert row["price"] == 62000
    assert row["transport"] == "websocket"
    coinbase = parse_coinbase_message({
        "type": "ticker", "product_id": "BTC-USD", "price": "62000", "open_24h": "61000",
        "high_24h": "63000", "low_24h": "60000", "volume_24h": "9", "time": "2026-11-15T00:00:00Z",
    })
    assert coinbase is not None
    assert coinbase["currency"] == "USD"
    assert reconnect_delay(1) == 1
    assert reconnect_delay(30) == 30


def test_stocks_and_etfs_stay_unavailable():
    classes = {item["asset_class"]: item for item in asset_classes()["classes"]}
    assert classes["crypto"]["status"] == "available"
    assert classes["stock"]["status"] == "unavailable"
    assert classes["etf"]["providers"] == []
