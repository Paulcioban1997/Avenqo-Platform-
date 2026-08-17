"""Exigences de données par capacité RetailSenseAI (Phase 26).

Ces exigences sont dérivées directement des mécanismes déjà en place
(`modules/retailsense/training_specs.py` et
`shared/ai_engine/task_resolution/service.py`), et non inventées : chaque
capacité liste les champs canoniques réellement nécessaires pour produire
une décision business exploitable.
"""

from __future__ import annotations

CAPABILITY_DATA_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "churn": ("customer_id", "order_timestamp"),
    "demand": ("product_id", "quantity", "order_timestamp"),
    "price": ("product_id", "unit_price"),
    "segmentation": ("customer_id", "quantity"),
    "recommendation": ("customer_id", "product_id", "quantity"),
    "sentiment": ("review_text",),
    "bad_review": ("review_text",),
    "anomaly": ("order_timestamp", "quantity"),
    "weekly_forecast": ("order_timestamp", "quantity"),
}
