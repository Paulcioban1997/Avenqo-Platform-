"""Frontière feature engineering — Phase 27.

Sépare explicitement les CHAMPS CANONIQUES (`CapabilityDataset.rows`, issus de
`PreparedCompanyDataset`) des FEATURES DÉRIVÉES calculées ici. Les features
dérivées (ex. `recency_days`, `frequency`, `monetary`) ne deviennent JAMAIS
des champs canoniques Phase 26 : elles ne vivent que dans ce module, en
entrée du moteur ML existant.

Ce module ne remplace aucun pipeline d'entraînement existant
(`modules/retailsense/tasks/`) : il documente et illustre la frontière pour
la capacité `segmentation` (RFM), qui est le cas explicitement demandé par
l'audit Phase 27.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from shared.ai_engine.capability_dataset.contracts import CapabilityDataset


@dataclass(frozen=True, slots=True)
class CustomerRFMFeatures:
    """Features dérivées (NON canoniques) pour la segmentation client."""

    customer_id: str
    recency_days: float
    frequency: int
    monetary: float


def _reverse_mapping(canonical_columns: dict[str, str]) -> dict[str, str]:
    return {canonical: original for original, canonical in canonical_columns.items()}


def _parse_timestamp(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def compute_segmentation_rfm_features(
    capability_dataset: CapabilityDataset,
) -> tuple[CustomerRFMFeatures, ...]:
    """Dérive Recency/Frequency/Monetary à partir des champs canoniques.

    Entrée canonique attendue : `customer_id`, `quantity` (requis par
    `segmentation`), et `order_timestamp`/`total_amount` quand disponibles
    (pas requis par `segmentation`, mais utilisés s'ils sont mappés — sinon
    `recency_days`/`monetary` restent `0.0`, sans lever d'erreur).
    """

    if capability_dataset.capability != "segmentation":
        raise ValueError(
            "compute_segmentation_rfm_features only applies to the "
            "'segmentation' capability."
        )

    reverse = _reverse_mapping(capability_dataset.canonical_columns)
    customer_col = reverse.get("customer_id")
    quantity_col = reverse.get("quantity")
    timestamp_col = reverse.get("order_timestamp")
    amount_col = reverse.get("total_amount")

    per_customer: dict[str, dict[str, object]] = {}
    reference_date: datetime | None = None

    for row in capability_dataset.rows:
        customer = row.get(customer_col) if customer_col else None
        if customer is None:
            continue
        timestamp = _parse_timestamp(row.get(timestamp_col)) if timestamp_col else None
        if timestamp is not None and (reference_date is None or timestamp > reference_date):
            reference_date = timestamp

    for row in capability_dataset.rows:
        customer = row.get(customer_col) if customer_col else None
        if customer is None:
            continue
        entry = per_customer.setdefault(
            str(customer), {"frequency": 0, "monetary": 0.0, "last_seen": None}
        )
        entry["frequency"] += 1
        if amount_col is not None:
            amount = row.get(amount_col)
            if isinstance(amount, (int, float)):
                entry["monetary"] += float(amount)
        if timestamp_col is not None:
            timestamp = _parse_timestamp(row.get(timestamp_col))
            if timestamp is not None:
                last_seen = entry["last_seen"]
                if last_seen is None or timestamp > last_seen:
                    entry["last_seen"] = timestamp

    features: list[CustomerRFMFeatures] = []
    for customer_id, entry in per_customer.items():
        recency_days = 0.0
        if reference_date is not None and entry["last_seen"] is not None:
            recency_days = (reference_date - entry["last_seen"]).total_seconds() / 86400.0
        features.append(
            CustomerRFMFeatures(
                customer_id=customer_id,
                recency_days=recency_days,
                frequency=int(entry["frequency"]),
                monetary=float(entry["monetary"]),
            )
        )
    return tuple(features)
