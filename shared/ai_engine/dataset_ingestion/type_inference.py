"""Inférence prudente du type sémantique d'une colonne (Phase 26).

Ne fait jamais confiance au seul dtype pandas : combine le nom de colonne et
le contenu réel des valeurs pour distinguer par exemple un identifiant
numérique long (`order_id=100234567`) d'un montant, ou un pourcentage d'un
simple nombre décimal.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date, datetime
from enum import Enum
from typing import Any

_IDENTIFIER_TOKENS = ("id", "code", "ref", "sku", "number", "uuid", "num")
_CURRENCY_TOKENS = ("price", "amount", "revenue", "cost", "total", "paid", "value", "salary", "spend")
_PERCENTAGE_TOKENS = ("percent", "rate", "ratio")
_CURRENCY_SYMBOLS = re.compile(r"[$€£]")
_PERCENTAGE_SUFFIX = re.compile(r"%\s*$")
_THOUSANDS_SEPARATED_NUMBER = re.compile(r"^-?[\d.,]+$")


class SemanticType(str, Enum):
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATETIME = "datetime"
    CATEGORICAL = "categorical"
    TEXT = "text"
    IDENTIFIER = "identifier"
    CURRENCY = "currency"
    PERCENTAGE = "percentage"
    UNKNOWN = "unknown"


def infer_semantic_type(column_name: str, values: Sequence[Any]) -> SemanticType:
    """Infère le type sémantique d'une colonne à partir de son nom et contenu."""

    present = [value for value in values if value is not None and str(value).strip() != ""]
    if not present:
        return SemanticType.UNKNOWN

    lowered_name = column_name.lower()
    total = len(present)
    distinct = len({str(value) for value in present})
    uniqueness_ratio = distinct / total if total else 0.0

    if all(isinstance(value, bool) for value in present):
        return SemanticType.BOOLEAN
    if all(_looks_boolean(value) for value in present):
        return SemanticType.BOOLEAN

    if all(isinstance(value, (datetime, date)) for value in present):
        return SemanticType.DATETIME
    if all(_looks_datetime(value) for value in present):
        return SemanticType.DATETIME

    if all(_looks_percentage(value) for value in present) and any(
        token in lowered_name for token in _PERCENTAGE_TOKENS
    ) or all(isinstance(value, str) and _PERCENTAGE_SUFFIX.search(value) for value in present):
        return SemanticType.PERCENTAGE

    numeric_values = [_to_number(value) for value in present]
    is_fully_numeric = all(number is not None for number in numeric_values)

    if is_fully_numeric:
        is_identifier_name = any(token in lowered_name for token in _IDENTIFIER_TOKENS)
        all_integers = all(float(number).is_integer() for number in numeric_values)  # type: ignore[arg-type]
        if is_identifier_name and uniqueness_ratio > 0.9 and all_integers:
            return SemanticType.IDENTIFIER
        if any(token in lowered_name for token in _CURRENCY_TOKENS) or any(
            isinstance(value, str) and _CURRENCY_SYMBOLS.search(value) for value in present
        ):
            return SemanticType.CURRENCY
        if all_integers:
            return SemanticType.INTEGER
        return SemanticType.FLOAT

    is_identifier_name = any(token in lowered_name for token in _IDENTIFIER_TOKENS)
    if is_identifier_name and uniqueness_ratio > 0.9:
        return SemanticType.IDENTIFIER

    if uniqueness_ratio <= 0.5 and distinct <= 50:
        return SemanticType.CATEGORICAL

    return SemanticType.TEXT


def _looks_boolean(value: Any) -> bool:
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)) and value in (0, 1):
        return True
    if isinstance(value, str):
        return value.strip().lower() in {"true", "false", "yes", "no", "y", "n", "0", "1"}
    return False


def _looks_datetime(value: Any) -> bool:
    if isinstance(value, (datetime, date)):
        return True
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def _looks_percentage(value: Any) -> bool:
    if isinstance(value, str) and _PERCENTAGE_SUFFIX.search(value):
        return True
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1


def _to_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = _CURRENCY_SYMBOLS.sub("", value).strip()
        cleaned = _PERCENTAGE_SUFFIX.sub("", cleaned).strip()
        cleaned = cleaned.replace(",", "")
        if not cleaned or not _THOUSANDS_SEPARATED_NUMBER.match(cleaned):
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None
