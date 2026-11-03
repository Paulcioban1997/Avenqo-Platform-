"""Bank of Canada foreign exchange reference rates service with in-memory caching and cross-rate computation.

Uses the official Bank of Canada Valet API:
https://www.bankofcanada.ca/valet/observations/{series}/json?recent=10

Never invents or assumes exchange rates. If the Bank of Canada endpoint is unreachable,
expired, or if no reliable published rate exists, conversion fails closed.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

logger = logging.getLogger("avenqo.fx.service")

# Official series codes from Bank of Canada Valet API
# https://www.bankofcanada.ca/valet/docs
BOC_SERIES_MAP: dict[str, str] = {
    "USD": "FXUSDCAD",
    "EUR": "FXEURCAD",
    "GBP": "FXGBPCAD",
    "JPY": "FXJPYCAD",
    "AUD": "FXAUDCAD",
    "CHF": "FXCHFCAD",
    "CNY": "FXCNYCAD",
    "MXN": "FXMXNCAD",
}

VALET_BASE_URL = "https://www.bankofcanada.ca/valet/observations/{series}/json?recent=10"


class FXRateError(Exception):
    """Raised when foreign exchange rates cannot be reliably determined."""
    def __init__(self, message: str, code: str = "FX_RATE_UNAVAILABLE") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


@dataclass(frozen=True)
class FXRateRecord:
    from_currency: str
    to_currency: str
    rate: Decimal
    source: str
    observation_date: str  # YYYY-MM-DD date of the official central bank observation
    fetched_at: datetime
    expires_at: datetime

    def is_expired(self, now: datetime | None = None) -> bool:
        check_time = now or datetime.now(timezone.utc)
        return check_time > self.expires_at


class BankOfCanadaFXService:
    """Retrieves, validates, caches, and cross-computes official exchange rates."""

    def __init__(
        self,
        cache_ttl_hours: int = 24,
        max_staleness_days: int = 7,
        timeout_seconds: float = 8.0,
    ) -> None:
        self.cache_ttl = timedelta(hours=cache_ttl_hours)
        self.max_staleness = timedelta(days=max_staleness_days)
        self.timeout = timeout_seconds
        self._cache: dict[tuple[str, str], FXRateRecord] = {}

    def clear_cache(self) -> None:
        self._cache.clear()

    def set_cached_rate(
        self,
        from_currency: str,
        to_currency: str,
        rate: Decimal,
        observation_date: str,
        source: str = "Banque du Canada - Taux officiel",
        ttl_hours: int = 24,
    ) -> FXRateRecord:
        """Injects or presets a certified rate (useful for hermetic tests)."""
        now = datetime.now(timezone.utc)
        record = FXRateRecord(
            from_currency=from_currency.upper().strip(),
            to_currency=to_currency.upper().strip(),
            rate=rate,
            source=source,
            observation_date=observation_date,
            fetched_at=now,
            expires_at=now + timedelta(hours=ttl_hours),
        )
        self._cache[(record.from_currency, record.to_currency)] = record
        return record

    async def get_rate_to_cad(self, currency: str) -> FXRateRecord | None:
        """Fetches official Bank of Canada rate to CAD (1 unit of currency = X CAD)."""
        curr = currency.upper().strip()
        now = datetime.now(timezone.utc)

        # 1. Parity case: CAD to CAD is always 1.00000000
        if curr == "CAD":
            return FXRateRecord(
                from_currency="CAD",
                to_currency="CAD",
                rate=Decimal("1.00000000"),
                source="Parité CAD",
                observation_date=now.date().isoformat(),
                fetched_at=now,
                expires_at=now + timedelta(days=365),
            )

        # 2. Check active cache
        cache_key = (curr, "CAD")
        cached = self._cache.get(cache_key)
        if cached and not cached.is_expired(now):
            return cached

        # 3. Check if supported by Bank of Canada series
        series = BOC_SERIES_MAP.get(curr)
        if not series:
            logger.warning("Devise non prise en charge par la Banque du Canada: %s", curr)
            return None

        # 4. Fetch from Bank of Canada Valet API
        url = VALET_BASE_URL.format(series=series)
        try:
            req = urllib.request.Request(
                url,
                headers={"Accept": "application/json", "User-Agent": "Avenqo-Platform/2.0"},
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status != 200:
                    logger.warning("Bank of Canada API returned status %s for series %s", resp.status, series)
                    return None
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            logger.warning("Échec de connexion à la Banque du Canada pour %s: %s", series, exc)
            # If network fails, check if stale cache exists within max_staleness
            if cached:
                staleness = now - cached.fetched_at
                if staleness <= self.max_staleness:
                    logger.info("Utilisation du taux en cache résiduel (%s jours) pour %s", staleness.days, curr)
                    return cached
            return None

        # 5. Parse latest observation
        observations = data.get("observations", [])
        if not observations:
            logger.warning("Aucune observation renvoyée par la Banque du Canada pour %s", series)
            return None

        # Get latest observation (last element in sorted chronological observations)
        latest_obs = observations[-1]
        obs_date_str = latest_obs.get("d")
        series_val = latest_obs.get(series, {})
        raw_val = series_val.get("v") if isinstance(series_val, dict) else None

        if not obs_date_str or not raw_val:
            logger.warning("Format d'observation invalide pour %s: %s", series, latest_obs)
            return None

        try:
            rate_dec = Decimal(str(raw_val))
            obs_date = date.fromisoformat(obs_date_str)
        except (InvalidOperation, ValueError) as exc:
            logger.warning("Valeur de taux invalide renvoyée par la Banque du Canada pour %s: %s", series, exc)
            return None

        # Check staleness: observation must not be older than max_staleness days
        if (now.date() - obs_date) > self.max_staleness:
            logger.warning("Taux de change Banque du Canada périmé pour %s (date: %s)", series, obs_date_str)
            return None

        record = FXRateRecord(
            from_currency=curr,
            to_currency="CAD",
            rate=rate_dec,
            source=f"Banque du Canada - API Valet ({series})",
            observation_date=obs_date_str,
            fetched_at=now,
            expires_at=now + self.cache_ttl,
        )
        self._cache[cache_key] = record
        return record

    async def get_exchange_rate(self, from_currency: str, to_currency: str = "CAD") -> FXRateRecord | None:
        """Computes direct or cross exchange rate between any two supported currencies."""
        src = from_currency.upper().strip()
        dst = to_currency.upper().strip()
        now = datetime.now(timezone.utc)

        if src == dst:
            return FXRateRecord(
                from_currency=src,
                to_currency=dst,
                rate=Decimal("1.00000000"),
                source=f"Parité {src}",
                observation_date=now.date().isoformat(),
                fetched_at=now,
                expires_at=now + timedelta(days=365),
            )

        if dst == "CAD":
            return await self.get_rate_to_cad(src)

        # Cross-rate calculation via CAD: Rate(A -> B) = Rate(A -> CAD) / Rate(B -> CAD)
        rate_a = await self.get_rate_to_cad(src)
        rate_b = await self.get_rate_to_cad(dst)

        if not rate_a or not rate_b:
            return None

        if rate_b.rate <= Decimal("0.00000000"):
            return None

        cross_rate = (rate_a.rate / rate_b.rate).quantize(Decimal("0.00000001"))
        earliest_obs_date = min(rate_a.observation_date, rate_b.observation_date)

        return FXRateRecord(
            from_currency=src,
            to_currency=dst,
            rate=cross_rate,
            source=f"Calcul croisé ({rate_a.source} / {rate_b.source})",
            observation_date=earliest_obs_date,
            fetched_at=now,
            expires_at=min(rate_a.expires_at, rate_b.expires_at),
        )
