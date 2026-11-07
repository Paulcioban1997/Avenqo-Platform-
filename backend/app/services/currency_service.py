"""Currency conversion service for multi-source consolidated retail analytics."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any


@dataclass(frozen=True, slots=True)
class ConversionResult:
    source_amount: Decimal
    source_currency: str
    target_amount: Decimal
    target_currency: str
    exchange_rate: Decimal
    formula: str


class CurrencyService:
    """Provides deterministic exchange rates and conversions across multi-store sources.
    
    Pivot rates are anchored to USD.
    USD -> CAD: 1.35
    USD -> EUR: 0.92
    USD -> GBP: 0.79
    USD -> AUD: 1.52
    USD -> JPY: 150.0
    USD -> CHF: 0.90
    """

    # Base pivot: Units of CURRENCY per 1 USD
    DEFAULT_RATES_PER_USD: dict[str, Decimal] = {
        "USD": Decimal("1.0"),
        "CAD": Decimal("1.35"),
        "EUR": Decimal("0.92"),
        "GBP": Decimal("0.79"),
        "AUD": Decimal("1.52"),
        "JPY": Decimal("150.0"),
        "CHF": Decimal("0.90"),
        "NZD": Decimal("1.65"),
    }

    def __init__(self, custom_rates_per_usd: dict[str, Decimal | float | str] | None = None) -> None:
        self._rates = dict(self.DEFAULT_RATES_PER_USD)
        if custom_rates_per_usd:
            for cur, rate in custom_rates_per_usd.items():
                self._rates[cur.upper()] = Decimal(str(rate))

    def get_rate(self, source_currency: str, target_currency: str) -> Decimal:
        src = source_currency.strip().upper()
        tgt = target_currency.strip().upper()
        if src == tgt:
            return Decimal("1.0")

        src_per_usd = self._rates.get(src)
        tgt_per_usd = self._rates.get(tgt)

        if src_per_usd is None or tgt_per_usd is None:
            # Fallback for unlisted currencies: 1.0
            return Decimal("1.0")

        # 1 unit of SRC in USD = 1 / src_per_usd
        # in TGT = (1 / src_per_usd) * tgt_per_usd = tgt_per_usd / src_per_usd
        return tgt_per_usd / src_per_usd

    def convert(
        self,
        amount: Decimal | float | int | str,
        source_currency: str,
        target_currency: str,
    ) -> ConversionResult:
        dec_amount = Decimal(str(amount or "0"))
        src = source_currency.strip().upper()
        tgt = target_currency.strip().upper()

        if src == tgt or not src:
            return ConversionResult(
                source_amount=dec_amount,
                source_currency=src or tgt,
                target_amount=dec_amount,
                target_currency=tgt,
                exchange_rate=Decimal("1.0"),
                formula=f"{dec_amount} {tgt}",
            )

        rate = self.get_rate(src, tgt)
        converted = (dec_amount * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        formula = f"{dec_amount} {src} * {rate:.4f} = {converted} {tgt}"

        return ConversionResult(
            source_amount=dec_amount,
            source_currency=src,
            target_amount=converted,
            target_currency=tgt,
            exchange_rate=rate,
            formula=formula,
        )
