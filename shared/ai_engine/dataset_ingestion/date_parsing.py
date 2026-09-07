"""Conservative column-aware parsing; ambiguous source values stay intact."""

import re
from collections.abc import Iterable
from datetime import date, datetime
from typing import Any

_SLASH = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")


def infer_date_order(values: Iterable[Any]) -> str | None:
    orders: set[str] = set()
    for value in values:
        match = _SLASH.fullmatch(str(value).strip())
        if not match:
            continue
        first, second, year = map(int, match.groups())
        try:
            if first > 12:
                datetime(year, second, first)
                orders.add("dmy")
            elif second > 12:
                datetime(year, first, second)
                orders.add("mdy")
        except ValueError:
            continue
    return next(iter(orders)) if len(orders) == 1 else None


def parse_date(value: Any, order: str | None = None) -> tuple[Any, bool]:
    if isinstance(value, datetime):
        return value.isoformat(), True
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time()).isoformat(), True
    if not isinstance(value, str):
        return value, False
    source = value.strip()
    try:
        return datetime.fromisoformat(source.replace("Z", "+00:00")).isoformat(), True
    except ValueError:
        pass
    try:
        if re.fullmatch(r"\d{4}/\d{1,2}/\d{1,2}", source):
            return datetime.strptime(source, "%Y/%m/%d").isoformat(), True
        match = _SLASH.fullmatch(source)
        if match:
            first, second, year = map(int, match.groups())
            # A column consensus is required for dates with two possible meanings.
            if order == "dmy" or (order is None and first > 12):
                return datetime(year, second, first).isoformat(), True
            if order == "mdy" or (order is None and second > 12) or first == second:
                return datetime(year, first, second).isoformat(), True
    except ValueError:
        pass
    return value, False
