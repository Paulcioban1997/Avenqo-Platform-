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
