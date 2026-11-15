"""Demo market math for Trading AI.

Every series is synthetic and labeled. Nothing here is a live quote, a
licensed feed, or an instruction to buy or sell.
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.trading import TradingWatchItem

DEMO_SOURCE = "avenqo-demo"
DEMO_INSTRUMENTS = (
    {"symbol": "DEMO-SPY", "name": "Démo indice large", "currency": "USD", "asset_class": "etf"},
    {"symbol": "DEMO-BTC", "name": "Démo crypto", "currency": "USD", "asset_class": "crypto"},
    {"symbol": "DEMO-EURUSD", "name": "Démo forex", "currency": "USD", "asset_class": "forex"},
)
_HORIZONS = {"1d": 1, "7d": 7, "30d": 30}


def instrument(symbol: str) -> dict | None:
    return next((item for item in DEMO_INSTRUMENTS if item["symbol"] == symbol), None)


def demo_closes(symbol: str, length: int = 160) -> list[float]:
    """Deterministic random walk. The same symbol always yields the same path."""
    seed = sum(ord(char) * (index + 1) for index, char in enumerate(symbol))
    generator = random.Random(seed)
    price = 100.0
    closes = []
    for _ in range(length):
        price = max(1.0, price * (1 + generator.uniform(-0.02, 0.021)))
        closes.append(round(price, 4))
    return closes


def candles(symbol: str) -> dict:
    item = instrument(symbol)
    if item is None:
        raise KeyError(symbol)
    closes = demo_closes(symbol)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    rows = []
    for index, close in enumerate(closes):
        open_price = closes[index - 1] if index else close
        high = max(open_price, close) * 1.002
        low = min(open_price, close) * 0.998
        rows.append({
            "time": (now - timedelta(days=len(closes) - index)).date().isoformat(),
            "open": round(open_price, 4),
            "high": round(high, 4),
            "low": round(low, 4),
            "close": close,
            "volume": 1000 + index,
        })
    return {
        "data_mode": "demo",
        "realtime": False,
        "market_status": "demo",
        "source": DEMO_SOURCE,
        "updated_at": now.isoformat(),
        "currency": item["currency"],
        "symbol": symbol,
        "candles": rows,
        "indicators": {
            "sma_20": _sma(closes, 20),
            "ema_12": _ema(closes, 12),
            "rsi_14": _rsi(closes, 14),
        },
    }


def forecast(symbol: str, horizon: str) -> dict:
    item = instrument(symbol)
    if item is None:
        raise KeyError(symbol)
    if horizon == "1h":
        return _unavailable(item, horizon, "insufficient_history")
    days = _HORIZONS.get(horizon)
    if days is None:
        raise KeyError(horizon)
    closes = demo_closes(symbol)
    samples = _samples(closes, days)
    if len(samples) < 40:
        return _unavailable(item, horizon, "insufficient_history")
    split = int(len(samples) * 0.7)
    train, test = samples[:split], samples[split:]
    if not train or not test:
        return _unavailable(item, horizon, "insufficient_history")
    weights = _ridge([row[0] for row in train], [row[1] for row in train])
    model_errors = [_absolute_error(weights, row) for row in test]
    baseline = sum(row[1] for row in train) / len(train)
    baseline_errors = [abs(row[1] - baseline) for row in test]
    model_mae = sum(model_errors) / len(model_errors)
    baseline_mae = sum(baseline_errors) / len(baseline_errors)
    directions = [(_predict(weights, row[0]) > 0) == (row[1] > 0) for row in test]
    payload = {
        "data_mode": "demo",
        "realtime": False,
        "source": DEMO_SOURCE,
        "symbol": symbol,
        "currency": item["currency"],
        "horizon": horizon,
        "validated": False,
        "status": "demo",
        "model": "ridge-returns-v1",
        "advice": None,
        "metrics": {
            "train_rows": len(train),
            "test_rows": len(test),
            "model_mae": round(model_mae, 6),
            "baseline_mae": round(baseline_mae, 6),
            "directional_accuracy": round(sum(directions) / len(directions), 4),
            "beats_baseline": model_mae < baseline_mae,
        },
        "estimate": None,
        "message": "Données synthétiques. Les métriques sont réelles, mais aucun prix estimé n'est affiché.",
    }
    return payload


def simulation(symbol: str) -> dict:
    """Paper SMA crossover on the demo path. No cash, no broker, no order."""
    item = instrument(symbol)
    if item is None:
        raise KeyError(symbol)
    closes = demo_closes(symbol)
    slow = _sma_series(closes, 20)
    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0
    wins = 0
    losses = 0
    position = 0
    entry = closes[0]
    for index in range(21, len(closes)):
        fast = sum(closes[index - 5:index]) / 5
        want = 1 if fast > slow[index] else 0
        if want != position:
            if position == 1:
                change = closes[index] / entry - 1
                equity *= 1 + change
                wins += change > 0
                losses += change <= 0
                peak = max(peak, equity)
                max_drawdown = max(max_drawdown, (peak - equity) / peak)
            position = want
            entry = closes[index]
    return {
        "data_mode": "demo",
        "simulation": True,
        "brokerage": False,
        "source": DEMO_SOURCE,
        "symbol": symbol,
        "currency": item["currency"],
        "net_return": round(equity - 1, 4),
        "max_drawdown": round(max_drawdown, 4),
        "wins": wins,
        "losses": losses,
        "message": "Simulation sur données synthétiques. Aucun ordre n'est envoyé.",
    }


def list_watch(session: Session, company_id: UUID, user_id: UUID) -> list[str]:
    rows = session.scalars(
        select(TradingWatchItem)
        .where(TradingWatchItem.company_id == company_id, TradingWatchItem.user_id == user_id)
        .order_by(TradingWatchItem.symbol)
    ).all()
    return [row.symbol for row in rows]


def add_watch(session: Session, company_id: UUID, user_id: UUID, symbol: str) -> list[str]:
    from backend.app.services.crypto_market import symbol_format

    try:
        symbol = symbol_format(symbol)
    except ValueError as exc:
        raise KeyError(symbol) from exc
    existing = session.scalar(
        select(TradingWatchItem).where(
            TradingWatchItem.company_id == company_id,
            TradingWatchItem.user_id == user_id,
            TradingWatchItem.symbol == symbol,
        )
    )
    if existing is None:
        session.add(TradingWatchItem(company_id=company_id, user_id=user_id, symbol=symbol))
        session.commit()
    return list_watch(session, company_id, user_id)


def remove_watch(session: Session, company_id: UUID, user_id: UUID, symbol: str) -> list[str]:
    row = session.scalar(
        select(TradingWatchItem).where(
            TradingWatchItem.company_id == company_id,
            TradingWatchItem.user_id == user_id,
            TradingWatchItem.symbol == symbol,
        )
    )
    if row is not None:
        session.delete(row)
        session.commit()
    return list_watch(session, company_id, user_id)


def _unavailable(item: dict, horizon: str, status: str) -> dict:
    return {
        "data_mode": "demo",
        "realtime": False,
        "source": DEMO_SOURCE,
        "symbol": item["symbol"],
        "currency": item["currency"],
        "horizon": horizon,
        "validated": False,
        "status": status,
        "model": "ridge-returns-v1",
        "advice": None,
        "estimate": None,
        "metrics": None,
        "message": "Pas assez d'historique démo pour cet horizon.",
    }


def _samples(closes: list[float], horizon: int) -> list[tuple[tuple[float, float, float], float]]:
    rows = []
    for index in range(20, len(closes) - horizon):
        future = math.log(closes[index + horizon] / closes[index])
        rows.append((_features(closes[: index + 1]), future))
    return rows


def _features(closes: list[float]) -> tuple[float, float, float]:
    last_return = math.log(closes[-1] / closes[-2])
    week = math.log(closes[-1] / closes[-6])
    window = [math.log(closes[index] / closes[index - 1]) for index in range(-10, 0)]
    variance = sum(value * value for value in window) / len(window)
    return (last_return, week, math.sqrt(variance))


def _ridge(features: list[tuple[float, float, float]], targets: list[float]) -> tuple[float, float, float, float]:
    width = 4
    matrix = [[0.0] * width for _ in range(width)]
    vector = [0.0] * width
    for row, target in zip(features, targets, strict=True):
        values = (1.0, *row)
        for left in range(width):
            vector[left] += values[left] * target
            for right in range(width):
                matrix[left][right] += values[left] * values[right]
    for index in range(1, width):
        matrix[index][index] += 0.01
    return _solve(matrix, vector)


def _solve(matrix: list[list[float]], vector: list[float]) -> tuple[float, float, float, float]:
    size = len(vector)
    working = [row[:] + [vector[index]] for index, row in enumerate(matrix)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda index: abs(working[index][column]))
        working[column], working[pivot] = working[pivot], working[column]
        divisor = working[column][column] or 1e-9
        for row in range(column + 1, size):
            factor = working[row][column] / divisor
            for cursor in range(column, size + 1):
                working[row][cursor] -= factor * working[column][cursor]
    solution = [0.0] * size
    for row in range(size - 1, -1, -1):
        known = sum(working[row][column] * solution[column] for column in range(row + 1, size))
        solution[row] = (working[row][size] - known) / (working[row][row] or 1e-9)
    return tuple(solution)  # type: ignore[return-value]


def _predict(weights: tuple[float, float, float, float], features: tuple[float, float, float]) -> float:
    return weights[0] + sum(weight * value for weight, value in zip(weights[1:], features, strict=True))


def _absolute_error(weights: tuple[float, float, float, float], row: tuple[tuple[float, float, float], float]) -> float:
    return abs(_predict(weights, row[0]) - row[1])


def _sma(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    return round(sum(values[-window:]) / window, 4)


def _sma_series(values: list[float], window: int) -> list[float]:
    series = []
    for index in range(len(values)):
        if index + 1 < window:
            series.append(values[index])
        else:
            series.append(sum(values[index + 1 - window:index + 1]) / window)
    return series


def _ema(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    alpha = 2 / (window + 1)
    current = sum(values[:window]) / window
    for value in values[window:]:
        current = alpha * value + (1 - alpha) * current
    return round(current, 4)


def _rsi(values: list[float], window: int) -> float | None:
    if len(values) <= window:
        return None
    gains = 0.0
    losses = 0.0
    for index in range(-window, 0):
        change = values[index] - values[index - 1]
        gains += max(change, 0)
        losses += max(-change, 0)
    if losses == 0:
        return 100.0
    relative = (gains / window) / (losses / window)
    return round(100 - 100 / (1 + relative), 2)
