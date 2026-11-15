from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.models import Base, TradingWatchItem
from backend.app.services.crypto_market import allows, normalize_kline, normalize_ticker
from backend.app.services.trading_engine import add_watch, candles, forecast, list_watch, simulation


def test_demo_candles_are_labeled_and_repeatable():
    first = candles("DEMO-SPY")
    second = candles("DEMO-SPY")
    assert first["data_mode"] == "demo"
    assert first["realtime"] is False
    assert first["source"] == "avenqo-demo"
    assert first["candles"] == second["candles"]
    assert first["currency"] == "USD"


def test_demo_forecast_never_prints_a_price():
    result = forecast("DEMO-SPY", "7d")
    assert result["advice"] is None
    assert result["data_mode"] == "demo"
    assert result["validated"] is False
    assert result["estimate"] is None
    assert result["metrics"]["train_rows"] > 0
    assert result["metrics"]["test_rows"] > 0
    hourly = forecast("DEMO-SPY", "1h")
    assert hourly["estimate"] is None
    assert hourly["validated"] is False


def test_simulation_never_places_an_order():
    result = simulation("DEMO-BTC")
    assert result["simulation"] is True
    assert result["brokerage"] is False


def test_live_ticker_parser_uses_the_exchange_numbers():
    ticker = normalize_ticker({
        "symbol": "BTCUSDT", "lastPrice": "64210.5", "priceChangePercent": "-1.25",
        "highPrice": "65000", "lowPrice": "64000", "volume": "1234.5", "closeTime": 1700000000000,
    })
    candle = normalize_kline([1700000000000, "100", "110", "90", "105", "12"])
    assert ticker["price"] == 64210.5
    assert ticker["source"] == "binance-public"
    assert candle["close"] == 105
    assert allows("BTCUSDT") is True
    assert allows("https://evil.example") is False


def test_watchlist_stays_inside_one_company(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'trading.db'}")
    Base.metadata.create_all(engine)
    company_a, company_b = uuid4(), uuid4()
    user_a, user_b = uuid4(), uuid4()
    with sessionmaker(bind=engine)() as session:
        assert add_watch(session, company_a, user_a, "BTCUSDT") == ["BTCUSDT"]
        assert list_watch(session, company_b, user_b) == []
        assert session.query(TradingWatchItem).count() == 1
