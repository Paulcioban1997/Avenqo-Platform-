from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from backend.app.config.settings import Settings
from backend.app.dependencies.subscription import require_active_subscription
from backend.main import create_application
from backend.app.dependencies.auth import CurrentIdentity, get_current_identity
from backend.app.routers.trading import require_trading


@pytest.fixture
def mock_identity():
    user = MagicMock()
    user.id = uuid4()
    user.company_id = uuid4()
    user.roles = ["ADMIN"]
    company = MagicMock()
    company.id = user.company_id
    company.display_currency = "CAD"
    user.company = company
    identity = CurrentIdentity(user=user, auth_session=None, raw_token="fake-token")
    return identity


def test_trading_ask_without_question(mock_identity):
    app = create_application()
    app.dependency_overrides[get_current_identity] = lambda: mock_identity
    app.dependency_overrides[require_trading] = lambda: mock_identity
    app.dependency_overrides[require_active_subscription] = lambda: None
    try:
        client = TestClient(app)
        with patch("backend.app.routers.trading.candles") as mock_candles, \
             patch("backend.app.routers.trading.factual_brief") as mock_brief, \
             patch("backend.app.routers.trading.experimental_study") as mock_study:
            mock_candles.return_value = {
                "candles": [{"open": 100, "close": 105, "high": 110, "low": 95, "time": 1000}],
                "indicators": {"rsi_14": 55.0},
            }
            mock_brief.return_value = {
                "symbol": "BTCUSDT",
                "text": "Analyse factuelle",
                "indicators": {"rsi_14": 55.0},
                "source": "binance-public",
                "freshness": "delayed",
                "change_percent": 5.0,
            }
            mock_study.return_value = {"test_return": 0.42}

            resp = client.post("/api/v1/trading/ask", json={"symbol": "BTCUSDT", "interval": "1h", "locale": "fr"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["symbol"] == "BTCUSDT"
            assert data["text"] == "Analyse factuelle"
            assert data["study"]["test_return"] == 0.42
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_trading_ask_with_question_calls_gemini(mock_identity):
    from backend.app.routers.trading import _explain_with_gemini

    settings = MagicMock(spec=Settings)
    settings.google_ai_api_key = "fake-key"
    settings.gemini_model = "gemini-2.5-flash"

    brief = {
        "text": "Fallback text",
        "indicators": {"rsi_14": 62.5, "sma_20": 85000, "ema_12": 85500, "macd": {"histogram": 12.5}, "bollinger": {"middle": 85000, "upper": 87000, "lower": 83000}},
        "source": "binance-public",
        "freshness": "delayed",
        "change_percent": 2.4,
    }

    with patch("backend.app.ai.llm.gemini_provider.GeminiProvider.generate", new_callable=AsyncMock) as mock_gen:
        gen_res = MagicMock()
        gen_res.content = "Le RSI à 62.5 indique une dynamique modérément haussière sans situation de surachat."
        mock_gen.return_value = gen_res

        result = await _explain_with_gemini(
            question="Quel est l'état du RSI ?",
            brief=brief,
            symbol="BTCUSDT",
            interval="1h",
            locale="fr",
            settings=settings,
        )

        assert "RSI à 62.5" in result
        mock_gen.assert_called_once()


def test_calculate_backtest_insufficient_history():
    from backend.app.services.market_feed import calculate_backtest

    res = calculate_backtest([100.0, 102.0, 101.0], strategy="crossover_sma")
    assert res["status"] == "insufficient_history"
    assert res["trades_count"] == 0
    assert res["strategy_return"] is None
    assert "insuffisant" in res["disclaimer"]


def test_calculate_backtest_independent_numerical_benchmark():
    from backend.app.services.market_feed import calculate_backtest

    # 9-bar series with known exact mathematical progression:
    # fast=2, slow=3, fee=0.001, slippage=0.0005, interval='1h'
    closes = [100.0, 100.0, 100.0, 100.0, 105.0, 110.0, 95.0, 90.0, 90.0]
    res = calculate_backtest(
        closes=closes,
        fast_period=2,
        slow_period=3,
        fee_rate=0.001,
        slippage_rate=0.0005,
        interval="1h",
    )

    assert res["status"] == "calculated"
    # Reliable is False: mathematical calculation finished != certified financial advice
    assert res["reliable"] is False
    assert res["data_integrity"]["status"] == "verified"
    assert res["data_integrity"]["continuous"] is True
    assert res["execution"]["status"] == "deterministic_completed"
    assert res["statistical_validation"]["status"] == "unverified"
    assert res["candles_count"] == 9
    assert res["evaluation_candles"] == 6  # bars 3 to 8
    assert res["start_price"] == 100.0
    assert res["end_price"] == 90.0

    # 1. Buy & Hold evaluated on exact same window [start_index=3, end=8]: 90/100 - 1 = -0.10 (-10.0%)
    assert res["holding_return"] == -0.10

    # 2. Strategy: enters at bar 4 (close=105), exits at bar 6 (close=95)
    # Entry price with slippage: 105 * 1.0005 = 105.0525
    # Exit price with slippage: 95 * 0.9995 = 94.9525
    assert len(res["closed_trades"]) == 1
    trade = res["closed_trades"][0]
    assert trade["entry_price"] == 105.0525
    assert trade["exit_price"] == 94.9525
    assert trade["entry_bar"] == 4
    assert trade["exit_bar"] == 6
    assert trade["bars_held"] == 2
    assert trade["win"] is False
    assert trade["net_return"] == -0.097949  # Exact net trade return
    assert res["open_position"] is None
    assert res["win_rate"] == 0.0

    # Final equity: strategy_return rounded to 4 decimals: -0.0979 (-9.79%)
    # Accurately penalizes entry and exit slippage on equity
    assert res["strategy_return"] == -0.0979

    # Max Drawdown occurred when equity dipped at bar 6
    assert res["max_drawdown"] == -0.1377


def test_calculate_backtest_equity_with_and_without_slippage():
    from backend.app.services.market_feed import calculate_backtest

    closes = [100.0, 100.0, 100.0, 100.0, 105.0, 110.0, 95.0, 90.0, 90.0]
    
    # Run without slippage
    res_no_slip = calculate_backtest(
        closes=closes,
        fast_period=2,
        slow_period=3,
        fee_rate=0.001,
        slippage_rate=0.0,
        interval="1h",
    )
    # Run with 0.1% slippage
    res_with_slip = calculate_backtest(
        closes=closes,
        fast_period=2,
        slow_period=3,
        fee_rate=0.001,
        slippage_rate=0.001,
        interval="1h",
    )

    # Slippage must strictly degrade equity and increase drawdown
    assert res_with_slip["strategy_return"] < res_no_slip["strategy_return"]
    assert res_with_slip["max_drawdown"] < res_no_slip["max_drawdown"]
    # Closed trade return rounded to 4 decimals must match equity return exactly
    assert round(res_with_slip["closed_trades"][0]["net_return"], 4) == res_with_slip["strategy_return"]


def test_calculate_backtest_crossover_sma_vs_crossover_ema():
    import math
    from backend.app.services.market_feed import calculate_backtest

    # 50-bar fluctuating series where EMA responds faster than SMA
    closes = [100.0 + 10.0 * math.sin(i * 0.4) for i in range(50)]
    
    res_sma = calculate_backtest(closes, strategy="crossover_sma", fast_period=4, slow_period=10)
    res_ema = calculate_backtest(closes, strategy="crossover_ema", fast_period=4, slow_period=10)

    assert res_sma["status"] == "calculated"
    assert res_ema["status"] == "calculated"
    assert res_sma["strategy"] == "crossover_sma"
    assert res_ema["strategy"] == "crossover_ema"

    # EMA weights recent prices more heavily, producing distinct execution and returns
    assert res_sma["strategy_return"] != res_ema["strategy_return"]


def test_calculate_backtest_invalid_series_rejection():
    from backend.app.services.market_feed import calculate_backtest

    # Series contains a non-positive / corrupted candle at index 3
    closes = [100.0, 102.0, 101.0, -10.0, 105.0, 108.0, 110.0, 112.0]
    res = calculate_backtest(closes, fast_period=2, slow_period=3)

    assert res["status"] == "invalid_series"
    assert res["reliable"] is False
    assert res["data_integrity"]["continuous"] is False
    assert "corrompue" in res["data_integrity"]["reason"] or "invalide" in res["data_integrity"]["reason"]
    assert res["strategy_return"] is None


def test_calculate_backtest_open_position():
    from backend.app.services.market_feed import calculate_backtest

    # Continues rising so signal stays long through end (8 bars >= slow_period 3 + 5)
    closes = [100.0, 100.0, 100.0, 100.0, 105.0, 110.0, 115.0, 120.0]
    res = calculate_backtest(
        closes=closes,
        fast_period=2,
        slow_period=3,
        fee_rate=0.001,
        slippage_rate=0.0005,
        interval="1h",
    )

    assert res["status"] == "calculated"
    assert res["reliable"] is False
    assert res["data_integrity"]["status"] == "verified"
    assert len(res["closed_trades"]) == 0
    assert res["open_position"] is not None
    open_pos = res["open_position"]
    assert open_pos["entry_price"] == 105.0525
    assert open_pos["current_price"] == 120.0
    assert open_pos["unrealized_return"] > 0.0
    assert open_pos["bars_held"] == 3
    assert res["win_rate"] is None  # No closed trades yet


def test_sharpe_annualization_across_intervals():
    from backend.app.services.market_feed import calculate_backtest

    # Synthetic alternating prices for 60 bars
    closes = [100.0 + (i % 5) * 2.0 for i in range(60)]

    res_1m = calculate_backtest(closes, fast_period=5, slow_period=15, interval="1m")
    res_1h = calculate_backtest(closes, fast_period=5, slow_period=15, interval="1h")
    res_4h = calculate_backtest(closes, fast_period=5, slow_period=15, interval="4h")
    res_1d = calculate_backtest(closes, fast_period=5, slow_period=15, interval="1d")

    # Confirm different annual factors applied based on interval
    assert res_1m["assumptions"]["annual_bars"] == 525600
    assert res_1h["assumptions"]["annual_bars"] == 8760
    assert res_4h["assumptions"]["annual_bars"] == 2190
    assert res_1d["assumptions"]["annual_bars"] == 365

    # Sharpe for 1m should scale higher due to sqrt(525600) vs sqrt(365) for 1d
    if res_1h["sharpe_ratio"] is not None and res_1d["sharpe_ratio"] is not None and res_1d["sharpe_ratio"] != 0:
        ratio = res_1m["assumptions"]["annual_factor"] / res_1d["assumptions"]["annual_factor"]
        assert round(ratio, 1) == round((525600 / 365) ** 0.5, 1)


def test_trading_backtest_endpoint_validations(mock_identity):
    from backend.app.dependencies.auth import get_current_identity
    from backend.app.dependencies.subscription import require_active_subscription
    from backend.app.routers.trading import require_trading
    from backend.main import create_application

    app = create_application()
    app.dependency_overrides[get_current_identity] = lambda: mock_identity
    app.dependency_overrides[require_trading] = lambda: mock_identity
    app.dependency_overrides[require_active_subscription] = lambda: None

    try:
        client = TestClient(app)

        # 1. fast_period >= slow_period rejected with 400
        resp = client.post(
            "/api/v1/trading/backtest",
            json={"symbol": "BTCUSDT", "interval": "1h", "fast_period": 30, "slow_period": 10},
        )
        assert resp.status_code == 400
        assert resp.json()["success"] is False

        # 2. unsupported strategy rejected with 400
        resp = client.post(
            "/api/v1/trading/backtest",
            json={"symbol": "BTCUSDT", "interval": "1h", "strategy": "invalid_strat"},
        )
        assert resp.status_code == 400
        assert resp.json()["success"] is False

        # 3. unsupported interval rejected with 400
        resp = client.post(
            "/api/v1/trading/backtest",
            json={"symbol": "BTCUSDT", "interval": "999h"},
        )
        assert resp.status_code == 400
        assert resp.json()["success"] is False
    finally:
        app.dependency_overrides.clear()



def test_trading_backtest_endpoint(mock_identity):
    from backend.app.dependencies.auth import get_current_identity
    from backend.app.dependencies.subscription import require_active_subscription
    from backend.app.routers.trading import require_trading
    from backend.main import create_application

    app = create_application()
    app.dependency_overrides[get_current_identity] = lambda: mock_identity
    app.dependency_overrides[require_trading] = lambda: mock_identity
    app.dependency_overrides[require_active_subscription] = lambda: None

    try:
        client = TestClient(app)
        synthetic_candles = [{"close": 100.0 + (i % 15) * 2.0} for i in range(100)]
        with patch("backend.app.routers.trading.candles") as mock_candles:
            mock_candles.return_value = {"candles": synthetic_candles}

            resp = client.post(
                "/api/v1/trading/backtest",
                json={"symbol": "BTCUSDT", "interval": "1h", "strategy": "crossover_sma"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["symbol"] == "BTCUSDT"
            assert data["interval"] == "1h"
            assert data["status"] == "calculated"
            assert data["candles_count"] == 100
            assert "strategy_return" in data
            assert "max_drawdown" in data
            assert "disclaimer" in data
    finally:
        app.dependency_overrides.clear()

