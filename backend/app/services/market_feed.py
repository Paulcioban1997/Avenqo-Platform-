"""Normalized public crypto quotes. Missing prices stay missing."""

from __future__ import annotations

import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

from backend.app.services.crypto_market import normalize_kline, normalize_ticker
from backend.app.services.market_stream import latest_quote, stream_health

_QUOTES = ("USDT", "USDC", "USD", "EUR")
_INTERVALS = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000, "1w": 604_800_000}
_COINBASE_GRANULARITY = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "1d": 86400}
_CACHE: dict[str, tuple[float, Any]] = {}
_POPULAR = ("BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "BNB", "AVAX", "LINK")


class MarketUnavailable(RuntimeError):
    pass


def watch_symbol(raw: str) -> str:
    base, quote = split_symbol(raw)
    if quote == "USDT":
        return f"{base}USDT"
    return f"{base}-{quote}"


def split_symbol(raw: str) -> tuple[str, str]:
    cleaned = raw.strip().upper().replace(" ", "").replace("_", "").replace("/", "")
    if not cleaned or any(char in cleaned for char in "\\?#&%"):
        raise ValueError(raw)
    if "-" in raw.upper():
        base, quote = raw.strip().upper().split("-", 1)
    else:
        quote = next((item for item in _QUOTES if cleaned.endswith(item) and len(cleaned) > len(item)), "")
        if not quote:
            raise ValueError(raw)
        base = cleaned[: -len(quote)]
    if not base.isalnum() or quote not in _QUOTES or not 2 <= len(base) <= 12:
        raise ValueError(raw)
    return base, quote


def canonical(raw: str) -> str:
    base, quote = split_symbol(raw)
    return f"{base}-{quote}"


def classify_freshness(transport: str, updated_at_ms: int, now_ms: int) -> str:
    age = now_ms - updated_at_ms
    if updated_at_ms <= 0 or age > 120_000:
        return "stale" if updated_at_ms else "unavailable"
    if transport == "websocket" and age <= 20_000:
        return "live"
    return "delayed"


def reconnect_note() -> dict:
    return stream_health()


def popular(quote: str = "USDT") -> list[dict[str, str]]:
    quote = quote.upper()
    if quote not in _QUOTES:
        raise ValueError(quote)
    return [{"symbol": watch_symbol(f"{base}-{quote}"), "base": base, "quote": quote, "asset_class": "crypto"} for base in _POPULAR]


def search(query: str, quote: str = "USDT") -> list[dict[str, str]]:
    needle = "".join(char for char in query.upper() if char.isalnum())[:20]
    if not needle:
        return popular(quote)
    rows = _cached(f"search:{quote}", 3600, lambda: _discover(quote))
    return [row for row in rows if needle in row["symbol"] or needle in row["base"]][:40]


def quotes(symbols: list[str], provider: str = "auto") -> dict:
    rows = []
    errors = []
    requested = symbols[:20] or [item["symbol"] for item in popular()]
    for symbol in requested:
        try:
            rows.append(live_quote(symbol, provider))
        except (MarketUnavailable, ValueError):
            errors.append(watch_symbol(symbol) if _safe(symbol) else "invalid")
    if not rows:
        raise MarketUnavailable("Cours indisponible")
    return {"quotes": rows, "missing": errors, "providers": stream_health()}


def live_quote(symbol: str, provider: str = "auto", now_ms: int | None = None) -> dict:
    base, quote = split_symbol(symbol)
    now = int(time.time() * 1000) if now_ms is None else now_ms
    order = _provider_order(provider, quote)
    stream_hit = _stream_hit(base, quote, now)
    if stream_hit is not None and (provider == "auto" or stream_hit["source"].startswith(provider)):
        return stream_hit
    last_error: Exception | None = None
    for name in order:
        try:
            row = _cached(f"quote:{name}:{base}-{quote}", 2, lambda name=name: _rest_quote(name, base, quote))
        except MarketUnavailable as exc:
            last_error = exc
            continue
        row = dict(row)
        row["freshness"] = classify_freshness(row["transport"], int(row["updated_at"]), now)
        row["prediction"] = None
        return row
    raise MarketUnavailable("Cours indisponible") from last_error


def candles(symbol: str, interval: str = "1m", limit: int = 120, provider: str = "auto") -> dict:
    if interval not in _INTERVALS:
        raise ValueError(interval)
    base, quote = split_symbol(symbol)
    bounded = min(max(limit, 30), 500)
    order = _provider_order(provider, quote)
    last_error: Exception | None = None
    for name in order:
        try:
            rows = _cached(
                f"candles:{name}:{base}-{quote}:{interval}:{bounded}",
                8,
                lambda name=name: _rest_candles(name, base, quote, interval, bounded),
            )
        except MarketUnavailable as exc:
            last_error = exc
            continue
        if len(rows) < 2:
            continue
        last = rows[-1]
        now = int(time.time() * 1000)
        freshness = "stale" if now - int(last["time"]) > _INTERVALS[interval] * 3 else "delayed"
        return {
            "symbol": watch_symbol(f"{base}-{quote}"),
            "currency": quote,
            "interval": interval,
            "source": f"{name}-public",
            "transport": "rest",
            "freshness": freshness,
            "data_mode": freshness,
            "realtime": False,
            "candles": rows,
            "indicators": indicator_snapshot([row["close"] for row in rows]),
            "prediction": None,
            "advice": None,
        }
    raise MarketUnavailable("Chandeliers indisponibles") from last_error


def rankings(quote: str = "USDT") -> dict:
    quote = quote.upper()
    if quote != "USDT":
        return {
            "source": "binance-public",
            "transport": "rest",
            "freshness": "unavailable",
            "currency": quote,
            "rows": [],
            "error": "Classement disponible uniquement en USDT via Binance public",
        }
    found = _CACHE.get("rankings:USDT")
    try:
        rows = _cached("rankings:USDT", 30, _binance_rankings)
        return {"source": "binance-public", "transport": "rest", "freshness": "delayed", "currency": "USDT", "rows": rows}
    except MarketUnavailable as exc:
        if found is not None:
            return {"source": "binance-public", "transport": "rest", "freshness": "stale", "currency": "USDT", "rows": found[1]}
        return {
            "source": "binance-public",
            "transport": "rest",
            "freshness": "unavailable",
            "currency": "USDT",
            "rows": [],
            "error": f"Données de marché indisponibles ({exc})",
        }


def asset_classes() -> dict:
    return {
        "classes": [
            {"asset_class": "crypto", "status": "available", "providers": ["binance-public", "coinbase-public"], "realtime": "websocket"},
            {"asset_class": "stock", "status": "unavailable", "providers": [], "reason": "Aucun flux actions autorisé."},
            {"asset_class": "etf", "status": "unavailable", "providers": [], "reason": "Aucun flux ETF autorisé."},
        ]
    }


def indicator_snapshot(closes: list[float]) -> dict:
    macd_line, signal, histogram = _macd(closes)
    middle, upper, lower = _bollinger(closes)
    return {
        "sma_20": _sma(closes, 20),
        "ema_12": _ema(closes, 12),
        "ema_26": _ema(closes, 26),
        "rsi_14": _rsi(closes, 14),
        "macd": {"line": macd_line, "signal": signal, "histogram": histogram},
        "bollinger": {"middle": middle, "upper": upper, "lower": lower},
        "kind": "calculation",
        "prediction": None,
    }


def factual_brief(symbol: str, interval: str = "1h", compare: str | None = None, locale: str = "fr") -> dict:
    primary = candles(symbol, interval, 200)
    other = candles(compare, interval, 200) if compare else None
    text = _brief_text(primary, other, locale)
    return {
        "kind": "calculation",
        "advice": None,
        "prediction": None,
        "reliable": False,
        "source": primary["source"],
        "freshness": primary["freshness"],
        "symbol": primary["symbol"],
        "interval": interval,
        "indicators": primary["indicators"],
        "comparison": None if other is None else {"symbol": other["symbol"], "indicators": other["indicators"], "change_percent": _span(other["candles"])},
        "change_percent": _span(primary["candles"]),
        "text": text,
    }


def experimental_study(closes: list[float]) -> dict:
    """Chronological SMA crossover versus holding. Not a trading recommendation."""
    if len(closes) < 80:
        return {"status": "insufficient_history", "reliable": False, "advice": None, "estimate": None, "prediction": None}
    split = int(len(closes) * 0.8)
    test = closes[split - 30:]
    strategy = _crossover_return(test)
    holding = (test[-1] / test[0]) - 1 if test[0] else 0
    return {
        "status": "experimental",
        "reliable": False,
        "advice": None,
        "estimate": None,
        "prediction": None,
        "test_return": round(strategy, 6),
        "holding_return": round(holding, 6),
        "message": "Résultat expérimental hors échantillon. Ce n'est pas un gain réel ni un conseil.",
    }


def resolve_quote(symbol: str, provider: str, fetchers: dict[str, Callable[[str], dict]], now_ms: int, stream: Callable[[str, str], dict | None] | None = None) -> dict:
    base, quote = split_symbol(symbol)
    key = f"{base}-{quote}"
    last_error: Exception | None = None
    for name in _provider_order(provider, quote):
        if stream is not None:
            hit = stream(name, key)
            if hit is not None and classify_freshness(hit.get("transport", ""), int(hit["updated_at"]), now_ms) == "live":
                return hit
        fetcher = fetchers.get(name)
        if fetcher is None:
            continue
        try:
            row = fetcher(key)
        except Exception as exc:
            last_error = exc
            continue
        if row.get("price") is None:
            last_error = MarketUnavailable(name)
            continue
        row = dict(row)
        row["freshness"] = classify_freshness(row.get("transport", "rest"), int(row["updated_at"]), now_ms)
        return row
    raise MarketUnavailable("Cours indisponible") from last_error


def _provider_order(provider: str, quote: str) -> tuple[str, ...]:
    if provider not in {"auto", "binance", "coinbase"}:
        raise ValueError(provider)
    if quote == "USD":
        return ("coinbase",) if provider in {"auto", "coinbase"} else ()
    if provider == "binance":
        return ("binance",)
    if provider == "coinbase":
        return ("coinbase",)
    return ("binance", "coinbase")


def _stream_hit(base: str, quote: str, now_ms: int) -> dict | None:
    key = f"{base}-{quote}"
    row = latest_quote(key) or latest_quote(f"{base}{quote}")
    if row is None:
        return None
    freshness = classify_freshness(str(row.get("transport", "")), int(row["updated_at"]), now_ms)
    if freshness != "live":
        return None
    hit = dict(row)
    hit["freshness"] = freshness
    hit["base"] = base
    hit["prediction"] = None
    return hit


def _rest_quote(provider: str, base: str, quote: str) -> dict:
    if provider == "binance":
        return _binance_quote(base, quote)
    if provider == "coinbase":
        return _coinbase_quote(base, quote)
    raise MarketUnavailable(provider)


def _rest_candles(provider: str, base: str, quote: str, interval: str, limit: int) -> list[dict]:
    if provider == "binance":
        return _binance_candles(base, quote, interval, limit)
    if provider == "coinbase":
        return _coinbase_candles(base, quote, interval)
    raise MarketUnavailable(provider)


def _binance_quote(base: str, quote: str) -> dict:
    if quote == "USD":
        raise MarketUnavailable("Binance USD")
    payload = _get("https://api.binance.com/api/v3/ticker/24hr", {"symbol": f"{base}{quote}"})
    row = normalize_ticker(payload)
    row["transport"] = "rest"
    row["canonical"] = f"{base}-{quote}"
    row["base"] = base
    return row


def _coinbase_quote(base: str, quote: str) -> dict:
    product = f"{base}-{quote}"
    ticker = _get(f"https://api.exchange.coinbase.com/products/{product}/ticker")
    stats = _get(f"https://api.exchange.coinbase.com/products/{product}/stats")
    price = float(ticker["price"])
    open_price = float(stats["open"])
    if price <= 0 or open_price <= 0:
        raise MarketUnavailable(product)
    return {
        "symbol": product,
        "canonical": product,
        "base": base,
        "price": price,
        "change_percent": round((price - open_price) / open_price * 100, 4),
        "high": float(stats["high"]),
        "low": float(stats["low"]),
        "volume": float(stats["volume"]),
        "updated_at": _iso_millis(str(ticker["time"])),
        "source": "coinbase-public",
        "transport": "rest",
        "currency": quote,
    }


def _binance_candles(base: str, quote: str, interval: str, limit: int) -> list[dict]:
    if quote == "USD":
        raise MarketUnavailable("Binance USD")
    payload = _get("https://api.binance.com/api/v3/klines", {"symbol": f"{base}{quote}", "interval": interval, "limit": limit})
    if not isinstance(payload, list) or not payload:
        raise MarketUnavailable("binance-candles")
    return [normalize_kline(row) for row in payload]


def _coinbase_candles(base: str, quote: str, interval: str) -> list[dict]:
    granularity = _COINBASE_GRANULARITY.get(interval)
    if granularity is None:
        raise MarketUnavailable("coinbase-interval")
    payload = _get(
        f"https://api.exchange.coinbase.com/products/{base}-{quote}/candles",
        {"granularity": granularity},
    )
    if not isinstance(payload, list) or not payload:
        raise MarketUnavailable("coinbase-candles")
    rows = [
        {"time": int(row[0]) * 1000, "low": float(row[1]), "high": float(row[2]), "open": float(row[3]), "close": float(row[4]), "volume": float(row[5])}
        for row in payload
    ]
    rows.sort(key=lambda item: item["time"])
    return rows


def _discover(quote: str) -> list[dict[str, str]]:
    if quote == "USD":
        payload = _get("https://api.exchange.coinbase.com/products")
        return [
            {"symbol": item["id"], "base": item["base_currency"], "quote": item["quote_currency"], "asset_class": "crypto"}
            for item in payload
            if item.get("quote_currency") == "USD" and item.get("status") == "online" and item.get("trading_disabled") is False
        ]
    payload = _get("https://api.binance.com/api/v3/exchangeInfo")
    return [
        {"symbol": f"{item['baseAsset']}{quote}", "base": item["baseAsset"], "quote": quote, "asset_class": "crypto"}
        for item in payload.get("symbols", [])
        if item.get("status") == "TRADING" and item.get("quoteAsset") == quote and item.get("isSpotTradingAllowed")
    ]


def _binance_rankings() -> list[dict]:
    payload = _get("https://api.binance.com/api/v3/ticker/24hr")
    rows = []
    for item in payload:
        symbol = str(item.get("symbol", ""))
        if not symbol.endswith("USDT"):
            continue
        try:
            row = normalize_ticker(item)
        except (KeyError, TypeError, ValueError):
            continue
        row["quote_volume"] = float(item.get("quoteVolume") or 0)
        row["base"] = symbol[:-4]
        rows.append(row)
    rows.sort(key=lambda item: item["quote_volume"], reverse=True)
    return rows[:25]


def _brief_text(primary: dict, other: dict | None, locale: str) -> str:
    french = locale.lower().startswith("fr")
    change = _span(primary["candles"])
    indicators = primary["indicators"]
    rsi = indicators["rsi_14"]
    macd = indicators["macd"]["histogram"]
    if french:
        text = (
            f"{primary['symbol']} varie de {change:.2f} % sur les bougies {primary['interval']} "
            f"fournies par {primary['source']} ({primary['freshness']}). "
            f"RSI 14 calculé : {rsi}. Histogramme MACD calculé : {macd}. "
            "Ce sont des calculs sur les prix reçus, pas une prévision et pas un conseil."
        )
    else:
        text = (
            f"{primary['symbol']} changed {change:.2f}% across the {primary['interval']} candles "
            f"from {primary['source']} ({primary['freshness']}). "
            f"Calculated RSI 14: {rsi}. Calculated MACD histogram: {macd}. "
            "These are calculations on retrieved prices, not a forecast and not advice."
        )
    if other is not None:
        other_change = _span(other["candles"])
        if french:
            text += f" Sur la même période, {other['symbol']} varie de {other_change:.2f} %."
        else:
            text += f" Over the same candles, {other['symbol']} changed {other_change:.2f}%."
    return text


def _span(rows: list[dict]) -> float:
    start = float(rows[0]["open"])
    end = float(rows[-1]["close"])
    if start == 0:
        return 0.0
    return (end - start) / start * 100


def _sma(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    return round(sum(values[-window:]) / window, 6)


def _ema(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    alpha = 2 / (window + 1)
    current = sum(values[:window]) / window
    for value in values[window:]:
        current = alpha * value + (1 - alpha) * current
    return round(current, 6)


def _ema_series(values: list[float], window: int) -> list[float]:
    alpha = 2 / (window + 1)
    current = sum(values[:window]) / window
    series = [current] * window
    for value in values[window:]:
        current = alpha * value + (1 - alpha) * current
        series.append(current)
    return series


def _rsi(values: list[float], window: int) -> float | None:
    if len(values) <= window:
        return None
    gains = losses = 0.0
    for index in range(-window, 0):
        change = values[index] - values[index - 1]
        gains += max(change, 0)
        losses += max(-change, 0)
    if losses == 0:
        return 100.0
    relative = (gains / window) / (losses / window)
    return round(100 - (100 / (1 + relative)), 4)


def _macd(values: list[float]) -> tuple[float | None, float | None, float | None]:
    if len(values) < 35:
        return None, None, None
    short = _ema_series(values, 12)
    long = _ema_series(values, 26)
    line = [left - right for left, right in zip(short, long, strict=True)]
    signal_series = _ema_series(line[25:], 9)
    signal = signal_series[-1]
    current = line[-1]
    return round(current, 6), round(signal, 6), round(current - signal, 6)


def _bollinger(values: list[float]) -> tuple[float | None, float | None, float | None]:
    if len(values) < 20:
        return None, None, None
    window = values[-20:]
    middle = sum(window) / 20
    variance = sum((value - middle) ** 2 for value in window) / 20
    width = math.sqrt(variance) * 2
    return round(middle, 6), round(middle + width, 6), round(middle - width, 6)


def _crossover_return(values: list[float]) -> float:
    position = 0.0
    equity = 1.0
    for index in range(30, len(values)):
        fast = sum(values[index - 10:index]) / 10
        slow = sum(values[index - 30:index]) / 30
        desired = 1.0 if fast > slow else 0.0
        if desired != position:
            position = desired
        if position and values[index - 1]:
            equity *= values[index] / values[index - 1]
    return equity - 1


def _iso_millis(value: str) -> int:
    from datetime import datetime

    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return int(parsed.timestamp() * 1000)


def _safe(symbol: str) -> bool:
    try:
        split_symbol(symbol)
    except ValueError:
        return False
    return True


def _cached(key: str, ttl: float, load: Callable[[], Any]) -> Any:
    found = _CACHE.get(key)
    now = time.monotonic()
    if found is not None and now - found[0] < ttl:
        return found[1]
    try:
        value = load()
        _CACHE[key] = (now, value)
        return value
    except Exception:
        if found is not None:
            return found[1]
        raise


def _get(url: str, query: dict | None = None) -> Any:
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"
    request = urllib.request.Request(url, headers={"User-Agent": "AvenqoTrading/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=6) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise MarketUnavailable(f"http-{exc.code}") from exc
    except Exception as exc:
        raise MarketUnavailable("provider") from exc
