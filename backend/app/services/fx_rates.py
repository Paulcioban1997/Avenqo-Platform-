"""Display-only FX. A missing rate leaves the original amount unchanged."""

from __future__ import annotations

import json
import time
import urllib.request
from typing import Callable

SUPPORTED = frozenset({
    "CAD", "USD", "EUR", "GBP", "CHF", "AUD", "JPY", "MXN", "NZD", "SEK", "NOK", "DKK",
    "PLN", "CZK", "HUF", "RON", "BGN", "TRY", "INR", "BRL", "ZAR", "SGD", "HKD", "CNY",
    "KRW", "ILS", "THB", "MYR", "PHP", "IDR", "ISK",
})
_CACHE: dict[str, tuple[float, float, str]] = {}


class RateUnavailable(RuntimeError):
    pass


def convert_amount(
    amount: float,
    source: str,
    target: str,
    *,
    rate: float | None = None,
    rate_date: str | None = None,
    on_date: str | None = None,
    fetch: Callable[..., tuple[float, str]] | None = None,
) -> dict:
    source = (source or "").upper()
    target = (target or "").upper()
    dated = _iso_date(on_date)
    valuation = "transaction_date" if dated else "current"
    original = {
        "amount": amount,
        "currency": source,
        "converted": False,
        "unavailable": False,
        "original_amount": amount,
        "original_currency": source,
        "rate": None,
        "rate_date": None,
        "source": None,
        "basis": None,
        "valuation": valuation,
    }
    if not target or source == target:
        return original
    if on_date and not dated:
        original["valuation"] = "transaction_date"
        original["unavailable"] = True
        return original
    basis = "USD" if source in {"USDT", "USDC"} else source
    if basis not in SUPPORTED or target not in SUPPORTED:
        original["unavailable"] = True
        return original
    if rate is None:
        try:
            loader = fetch or frankfurter_rate
            rate, rate_date = loader(basis, target, dated) if dated else loader(basis, target)
        except Exception:
            original["unavailable"] = True
            return original
    if rate is None or rate <= 0:
        original["unavailable"] = True
        return original
    return {
        "amount": round(float(amount) * float(rate), 6),
        "currency": target,
        "converted": True,
        "unavailable": False,
        "original_amount": amount,
        "original_currency": source,
        "rate": float(rate),
        "rate_date": rate_date,
        "source": "ecb-frankfurter",
        "basis": basis,
        "valuation": valuation,
    }


def quote_items(display_currency: str | None, items: list[dict], fetch: Callable[..., tuple[float, str]] | None = None) -> list[dict]:
    """Convert for one company display currency. Items cannot name another company."""
    target = (display_currency or "").upper()
    quoted = []
    for item in items[:40]:
        row = convert_amount(
            float(item.get("amount") or 0),
            str(item.get("currency") or ""),
            target,
            on_date=item.get("on_date"),
            fetch=fetch,
        )
        row["id"] = str(item.get("id") or "")[:80]
        quoted.append(row)
    return quoted


def _iso_date(value: str | None) -> str | None:
    if not value:
        return None
    day = str(value)[:10]
    if len(day) == 10 and day[4] == "-" and day[7] == "-" and day.replace("-", "").isdigit():
        return day
    return None


def frankfurter_rate(source: str, target: str, on_date: str | None = None) -> tuple[float, str]:
    day = _iso_date(on_date)
    path = day or "latest"
    key = f"{source}:{target}:{path}"
    found = _CACHE.get(key)
    now = time.monotonic()
    if found is not None and now - found[0] < 3600:
        return found[1], found[2]
    request = urllib.request.Request(
        f"https://api.frankfurter.app/{path}?from={source}&to={target}",
        headers={"User-Agent": "AvenqoTrading/1.0"},
    )
    with urllib.request.urlopen(request, timeout=6) as response:
        payload = json.loads(response.read().decode("utf-8"))
    rate = float(payload["rates"][target])
    rate_date = str(payload["date"])
    if rate <= 0:
        raise RateUnavailable(target)
    _CACHE[key] = (now, rate, rate_date)
    return rate, rate_date
