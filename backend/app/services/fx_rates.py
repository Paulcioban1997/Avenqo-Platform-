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
    fetch: Callable[[str, str], tuple[float, str]] | None = None,
) -> dict:
    source = (source or "").upper()
    target = (target or "").upper()
    original = {
        "amount": amount,
        "currency": source,
        "converted": False,
        "original_amount": amount,
        "original_currency": source,
        "rate": None,
        "rate_date": None,
        "source": None,
        "basis": None,
    }
    if not target or source == target:
        return original
    basis = "USD" if source in {"USDT", "USDC"} else source
    if basis not in SUPPORTED or target not in SUPPORTED:
        return original
    if rate is None:
        try:
            rate, rate_date = (fetch or frankfurter_rate)(basis, target)
        except Exception:
            return original
    if rate is None or rate <= 0:
        return original
    return {
        "amount": round(float(amount) * float(rate), 6),
        "currency": target,
        "converted": True,
        "original_amount": amount,
        "original_currency": source,
        "rate": float(rate),
        "rate_date": rate_date,
        "source": "ecb-frankfurter",
        "basis": basis,
    }


def frankfurter_rate(source: str, target: str) -> tuple[float, str]:
    key = f"{source}:{target}"
    found = _CACHE.get(key)
    now = time.monotonic()
    if found is not None and now - found[0] < 3600:
        return found[1], found[2]
    request = urllib.request.Request(
        f"https://api.frankfurter.app/latest?from={source}&to={target}",
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
