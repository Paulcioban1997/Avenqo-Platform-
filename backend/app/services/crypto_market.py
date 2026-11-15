"""Public Binance spot prices. No key, no orders, no invented quotes."""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from typing import Any

_ORIGIN = "https://api.binance.com"
_INTERVALS = {"1m", "5m", "15m", "1h", "4h", "1d"}
_PAIRS: tuple[dict[str, str], ...] = ()
_PAIRS_AT = 0.0
_CACHE: dict[str, tuple[float, Any]] = {}
_TTL = {"pairs": 3600.0, "candles": 8.0, "quotes": 2.0}


class MarketUnavailable(RuntimeError):
    pass


def popular() -> list[dict[str, str]]:
    return [
        {"symbol": "BTCUSDT", "base": "BTC", "quote": "USDT"},
        {"symbol": "ETHUSDT", "base": "ETH", "quote": "USDT"},
        {"symbol": "SOLUSDT", "base": "SOL", "quote": "USDT"},
        {"symbol": "XRPUSDT", "base": "XRP", "quote": "USDT"},
        {"symbol": "BNBUSDT", "base": "BNB", "quote": "USDT"},
        {"symbol": "ADAUSDT", "base": "ADA", "quote": "USDT"},
        {"symbol": "DOGEUSDT", "base": "DOGE", "quote": "USDT"},
        {"symbol": "AVAXUSDT", "base": "AVAX", "quote": "USDT"},
    ]


def search(query: str) -> list[dict[str, str]]:
    needle = "".join(char for char in query.upper() if char.isalnum())[:20]
    pairs = _pairs()
    if not needle:
        return popular()
    return [pair for pair in pairs if needle in pair["symbol"] or needle in pair["base"]][:30]


def candles(symbol: str, interval: str = "1m", limit: int = 120) -> dict:
    pair = _require(symbol)
    if interval not in _INTERVALS:
        raise ValueError(interval)
    bounded = min(max(limit, 20), 500)
    key = f"candles:{pair}:{interval}:{bounded}"
    rows = _cached(key, _TTL["candles"], lambda: _klines(pair, interval, bounded))
    return {
        "data_mode": "live",
        "realtime": True,
        "delayed": False,
        "market_status": "open",
        "source": "binance-public",
        "symbol": pair,
        "currency": "USDT",
        "interval": interval,
        "candles": rows,
    }


def quotes(symbols: list[str]) -> dict:
    pairs = [_require(symbol) for symbol in symbols[:20]]
    if not pairs:
        pairs = [item["symbol"] for item in popular()]
    key = "quotes:" + ",".join(pairs)
    rows = _cached(key, _TTL["quotes"], lambda: _tickers(pairs))
    return {"data_mode": "live", "source": "binance-public", "currency": "USDT", "quotes": rows}


def symbol_format(symbol: str) -> str:
    cleaned = symbol.strip().upper()
    if not cleaned.endswith("USDT") or not cleaned[:-4].isalnum() or not 6 <= len(cleaned) <= 24:
        raise ValueError(symbol)
    return cleaned


def allows(symbol: str) -> bool:
    try:
        symbol_format(symbol)
    except ValueError:
        return False
    return True


def normalize_ticker(payload: dict) -> dict:
    return {
        "symbol": str(payload["symbol"]),
        "price": float(payload["lastPrice"]),
        "change_percent": float(payload["priceChangePercent"]),
        "high": float(payload["highPrice"]),
        "low": float(payload["lowPrice"]),
        "volume": float(payload["volume"]),
        "updated_at": int(payload["closeTime"]),
        "source": "binance-public",
        "currency": "USDT",
    }


def normalize_kline(row: list) -> dict:
    return {
        "time": int(row[0]),
        "open": float(row[1]),
        "high": float(row[2]),
        "low": float(row[3]),
        "close": float(row[4]),
        "volume": float(row[5]),
    }


def _require(symbol: str) -> str:
    cleaned = symbol_format(symbol)
    if _PAIRS and cleaned not in {pair["symbol"] for pair in _PAIRS}:
        raise KeyError(cleaned)
    return cleaned


def _pairs() -> tuple[dict[str, str], ...]:
    global _PAIRS, _PAIRS_AT
    if _PAIRS and time.monotonic() - _PAIRS_AT < _TTL["pairs"]:
        return _PAIRS
    payload = _get("/api/v3/exchangeInfo")
    pairs = tuple(
        {"symbol": item["symbol"], "base": item["baseAsset"], "quote": "USDT"}
        for item in payload.get("symbols", [])
        if item.get("status") == "TRADING" and item.get("quoteAsset") == "USDT" and item.get("isSpotTradingAllowed")
    )
    if not pairs:
        raise MarketUnavailable("Binance n'a retourné aucune paire USDT")
    _PAIRS = pairs
    _PAIRS_AT = time.monotonic()
    return pairs


def _klines(symbol: str, interval: str, limit: int) -> list[dict]:
    payload = _get("/api/v3/klines", {"symbol": symbol, "interval": interval, "limit": limit})
    if not isinstance(payload, list) or not payload:
        raise MarketUnavailable("Aucune bougie Binance")
    return [normalize_kline(row) for row in payload]


def _tickers(symbols: list[str]) -> list[dict]:
    payload = _get("/api/v3/ticker/24hr", {"symbols": json.dumps(symbols, separators=(",", ":"))})
    if isinstance(payload, dict):
        payload = [payload]
    return [normalize_ticker(item) for item in payload]


def _cached(key: str, ttl: float, load):
    found = _CACHE.get(key)
    now = time.monotonic()
    if found is not None and now - found[0] < ttl:
        return found[1]
    value = load()
    _CACHE[key] = (now, value)
    return value


def _get(path: str, query: dict | None = None) -> Any:
    url = _ORIGIN + path
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"
    request = urllib.request.Request(url, headers={"User-Agent": "AvenqoTrading/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=6) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise MarketUnavailable("Cours Binance indisponible") from exc
