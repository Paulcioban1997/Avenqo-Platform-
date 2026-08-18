"""Exceptions métier Phase 27 — messages toujours business, jamais techniques.

BON  : "Sentiment analysis requires customer feedback text."
MAUVAIS : "Transformer tokenizer feature column missing."
"""

from __future__ import annotations

CAPABILITY_LABELS: dict[str, str] = {
    "churn": "Customer churn prediction",
    "segmentation": "Customer segmentation",
    "recommendation": "Product recommendations",
    "sentiment": "Sentiment analysis",
    "demand": "Demand forecasting",
    "weekly_forecast": "Weekly forecast",
    "price": "Price analysis",
    "bad_review": "Bad review detection",
    "anomaly": "Anomaly detection",
}

FIELD_LABELS: dict[str, str] = {
    "customer_id": "customer identifier",
    "order_id": "order identifier",
    "product_id": "product identifier",
    "order_timestamp": "order date/time",
    "quantity": "quantity sold",
    "unit_price": "unit price",
    "total_amount": "order total amount",
    "review_text": "customer feedback text",
    "review_score": "review score",
    "churn_flag": "churn flag",
}


def capability_label(capability: str) -> str:
    return CAPABILITY_LABELS.get(capability, capability.replace("_", " ").title())


def field_labels(fields: tuple[str, ...]) -> str:
    return ", ".join(FIELD_LABELS.get(field, field) for field in fields)


class CapabilityDatasetError(Exception):
    """Base des erreurs métier Phase 27 (jamais de message technique)."""


class UnknownCapability(CapabilityDatasetError):
    """La capacité demandée n'existe pas dans le registre RetailSenseAI."""


class CapabilityNotReady(CapabilityDatasetError):
    """La capacité ne peut pas être exécutée avec les données disponibles."""


class MissingCapabilityFields(CapabilityNotReady):
    """Un ou plusieurs champs canoniques requis sont absents du mapping."""

    def __init__(self, capability: str, missing_fields: tuple[str, ...]) -> None:
        self.capability = capability
        self.missing_fields = missing_fields
        message = f"{capability_label(capability)} requires {field_labels(missing_fields)}."
        super().__init__(message)


class InvalidCapabilityDataset(CapabilityDatasetError):
    """Les champs requis sont mappés mais aucune ligne exploitable n'existe."""

    def __init__(self, capability: str) -> None:
        self.capability = capability
        message = (
            f"{capability_label(capability)} has no usable rows for the "
            "data currently available."
        )
        super().__init__(message)
