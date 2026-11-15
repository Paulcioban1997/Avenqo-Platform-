"""Public exchange websockets. No API key, no customer identifiers in logs."""

from __future__ import annotations

import base64
import json
import logging
import os
import socket
import ssl
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

BINANCE_HOST = "stream.binance.com"
COINBASE_HOST = "ws-feed.exchange.coinbase.com"
_STREAMS = (
    "btcusdt@miniTicker",
    "ethusdt@miniTicker",
    "solusdt@miniTicker",
    "xrpusdt@miniTicker",
    "adausdt@miniTicker",
    "dogeusdt@miniTicker",
    "bnbusdt@miniTicker",
    "avaxusdt@miniTicker",
    "linkusdt@miniTicker",
)
_COINBASE_PRODUCTS = ("BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "ADA-USD", "DOGE-USD", "AVAX-USD", "LINK-USD")

_LOCK = threading.Lock()
_STOP = threading.Event()
_THREADS: list[threading.Thread] = []
_QUOTES: dict[str, dict[str, Any]] = {}
_HEALTH = {
    "binance": {"connected": False, "reconnects": 0, "last_error": None, "last_message_at": 0},
    "coinbase": {"connected": False, "reconnects": 0, "last_error": None, "last_message_at": 0},
}


def reconnect_delay(attempt: int) -> float:
    return min(30.0, 0.5 * (2 ** min(max(attempt, 1), 6)))


def parse_binance_message(payload: dict) -> dict | None:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if not isinstance(data, dict) or data.get("e") != "24hrMiniTicker":
        return None
    symbol = str(data["s"])
    price = float(data["c"])
    open_price = float(data["o"])
    if price <= 0 or open_price <= 0:
        raise ValueError(symbol)
    change = (price - open_price) / open_price * 100
    return {
        "symbol": symbol,
        "canonical": _binance_canonical(symbol),
        "price": price,
        "change_percent": round(change, 4),
        "high": float(data["h"]),
        "low": float(data["l"]),
        "volume": float(data["v"]),
        "updated_at": int(data["E"]),
        "source": "binance-public",
        "transport": "websocket",
        "currency": symbol[-4:] if symbol.endswith("USDT") else symbol[-3:],
    }


def parse_coinbase_message(payload: dict) -> dict | None:
    if payload.get("type") != "ticker" or not payload.get("product_id"):
        return None
    price = float(payload["price"])
    open_price = float(payload["open_24h"])
    if price <= 0 or open_price <= 0:
        raise ValueError(payload.get("product_id"))
    product = str(payload["product_id"])
    base, quote = product.split("-", 1)
    return {
        "symbol": product,
        "canonical": product,
        "base": base,
        "price": price,
        "change_percent": round((price - open_price) / open_price * 100, 4),
        "high": float(payload["high_24h"]),
        "low": float(payload["low_24h"]),
        "volume": float(payload["volume_24h"]),
        "updated_at": _iso_millis(str(payload["time"])),
        "source": "coinbase-public",
        "transport": "websocket",
        "currency": quote,
    }


def latest_quote(canonical: str) -> dict | None:
    with _LOCK:
        row = _QUOTES.get(canonical)
        return dict(row) if row else None


def stream_health() -> dict:
    with _LOCK:
        return {name: dict(item) for name, item in _HEALTH.items()}


def start_market_stream() -> None:
    if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("AVENQO_MARKET_STREAM", "1") == "0":
        return
    global _THREADS
    if any(thread.is_alive() for thread in _THREADS):
        return
    _STOP.clear()
    _THREADS = [
        threading.Thread(target=_binance_loop, name="avenqo-binance-stream", daemon=True),
        threading.Thread(target=_coinbase_loop, name="avenqo-coinbase-stream", daemon=True),
    ]
    for thread in _THREADS:
        thread.start()


def stop_market_stream() -> None:
    _STOP.set()
    for thread in list(_THREADS):
        thread.join(timeout=2)


def _binance_canonical(symbol: str) -> str:
    if symbol.endswith("USDT"):
        return f"{symbol[:-4]}-USDT"
    return symbol


def _iso_millis(value: str) -> int:
    from datetime import datetime

    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return int(parsed.timestamp() * 1000)


def _remember(provider: str, row: dict) -> None:
    with _LOCK:
        _QUOTES[row["canonical"]] = row
        if row["canonical"].endswith("-USDT"):
            _QUOTES[row["canonical"].replace("-", "")] = row
        state = _HEALTH[provider]
        state["connected"] = True
        state["last_error"] = None
        state["last_message_at"] = row["updated_at"]


def _mark_down(provider: str, attempt: int) -> None:
    with _LOCK:
        state = _HEALTH[provider]
        state["connected"] = False
        state["reconnects"] = attempt
        state["last_error"] = f"{provider}-stream"
    logger.warning("Market stream reconnect provider=%s attempt=%s", provider, attempt)


def _binance_loop() -> None:
    attempt = 0
    path = "/stream?streams=" + "/".join(_STREAMS)
    while not _STOP.is_set():
        try:
            _read_socket(BINANCE_HOST, path, "binance", parse_binance_message)
            attempt = 0
        except Exception:
            attempt += 1
            _mark_down("binance", attempt)
            if _STOP.wait(reconnect_delay(attempt)):
                return


def _coinbase_loop() -> None:
    attempt = 0
    while not _STOP.is_set():
        try:
            _read_socket(COINBASE_HOST, "/", "coinbase", parse_coinbase_message, _coinbase_hello())
            attempt = 0
        except Exception:
            attempt += 1
            _mark_down("coinbase", attempt)
            if _STOP.wait(reconnect_delay(attempt)):
                return


def _coinbase_hello() -> bytes:
    payload = json.dumps({
        "type": "subscribe",
        "product_ids": list(_COINBASE_PRODUCTS),
        "channels": ["ticker"],
    }).encode()
    return payload


def _read_socket(host: str, path: str, provider: str, parser, opening: bytes | None = None) -> None:
    raw = socket.create_connection((host, 443), timeout=10)
    try:
        sock = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
        sock.settimeout(25)
        _handshake(sock, host, path)
        if opening is not None:
            _send_frame(sock, 1, opening)
        while not _STOP.is_set():
            opcode, payload = _read_frame(sock)
            if opcode == 8:
                raise ConnectionError("closed")
            if opcode == 9:
                _send_frame(sock, 10, payload)
                continue
            if opcode != 1 or not payload:
                continue
            try:
                row = parser(json.loads(payload.decode("utf-8")))
            except (ValueError, KeyError, TypeError, json.JSONDecodeError):
                continue
            if row is not None:
                _remember(provider, row)
    finally:
        raw.close()


def _handshake(sock: socket.socket, host: str, path: str) -> None:
    key = base64.b64encode(os.urandom(16)).decode()
    request = (
        f"GET {path} HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\n"
        f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
    )
    sock.sendall(request.encode())
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("handshake")
        data += chunk
        if len(data) > 8192:
            raise ConnectionError("handshake")
    if b" 101 " not in data.split(b"\r\n", 1)[0]:
        raise ConnectionError("handshake")


def _read_exact(sock: socket.socket, size: int) -> bytes:
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise ConnectionError("socket")
        data += chunk
    return data


def _read_frame(sock: socket.socket) -> tuple[int, bytes]:
    header = _read_exact(sock, 2)
    opcode = header[0] & 0x0F
    length = header[1] & 0x7F
    if length == 126:
        length = int.from_bytes(_read_exact(sock, 2), "big")
    elif length == 127:
        length = int.from_bytes(_read_exact(sock, 8), "big")
    if length > 1_000_000:
        raise ConnectionError("frame")
    return opcode, _read_exact(sock, length) if length else b""


def _send_frame(sock: socket.socket, opcode: int, payload: bytes) -> None:
    mask = os.urandom(4)
    masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    length = len(payload)
    header = bytearray([0x80 | opcode])
    if length < 126:
        header.append(0x80 | length)
    elif length < 65536:
        header.append(0x80 | 126)
        header.extend(length.to_bytes(2, "big"))
    else:
        header.append(0x80 | 127)
        header.extend(length.to_bytes(8, "big"))
    sock.sendall(bytes(header) + mask + masked)
