from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import Any

from modules.catalog import MODULES_BY_CODE


class TaskResolutionService:
    """Détecte les capacités IA réelles d'un dataset puis les intersecte avec le module."""

    _DATASET_TASKS: tuple[str, ...] = (
        "forecasting",
        "classification",
        "regression",
        "segmentation",
        "recommendation",
        "anomaly_detection",
        "sentiment_analysis",
    )

    def resolve_dataset_capabilities(self, rows: Iterable[Mapping[str, Any]]) -> set[str]:
        materialized = [dict(row) for row in rows]
        if not materialized:
            return set()

        keys = tuple(dict.fromkeys(key for row in materialized for key in row))
        lower_keys = {key.lower(): key for key in keys}

        normalized = [
            {lower_key: value for key, value in row.items() for lower_key in (key.lower(),)}
            for row in materialized
        ]

        capabilities: set[str] = set()

        if self._has_time_signal(normalized):
            capabilities.add("forecasting")
        if self._has_classification_target(normalized):
            capabilities.add("classification")
        if self._has_regression_target(normalized):
            capabilities.add("regression")
        if self._has_segmentation_signal(normalized):
            capabilities.add("segmentation")
        if self._has_recommendation_signal(normalized):
            capabilities.add("recommendation")
        if self._has_anomaly_signal(normalized):
            capabilities.add("anomaly_detection")
        if self._has_sentiment_signal(normalized):
            capabilities.add("sentiment_analysis")

        return capabilities

    def resolve_tasks_for_module(self, module_code: str, rows: Iterable[Mapping[str, Any]]) -> tuple[str, ...]:
        dataset_capabilities = self.resolve_dataset_capabilities(rows)
        module = MODULES_BY_CODE.get(module_code)
        if module is None:
            return tuple()

        module_capabilities = {self._normalize_module_task(task.code) for task in module.tasks}

        resolved = dataset_capabilities & module_capabilities
        return tuple(sorted(resolved))

    def _has_time_signal(self, rows: Sequence[Mapping[str, Any]]) -> bool:
        for row in rows:
            for key, value in row.items():
                normalized_key = str(key).lower()
                if normalized_key in {"date", "time", "datetime", "timestamp", "order_date", "created_at"}:
                    try:
                        datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                        return True
                    except Exception:
                        continue
        numeric = self._collect_numeric_values(rows)
        normalized_numeric = {str(key).lower(): count for key, count in numeric.items()}
        return len(normalized_numeric) >= 2 and any(
            key in {"sales", "revenue", "demand", "orders", "units", "quantity", "transactions", "total"}
            for key in normalized_numeric
        )

    def _has_classification_target(self, rows: Sequence[Mapping[str, Any]]) -> bool:
        for column in self._candidate_target_columns(rows):
            values = [row.get(column) for row in rows if column in row]
            non_null = [value for value in values if value is not None]
            if len(non_null) < 3:
                continue
            unique = {str(value) for value in non_null}
            # Répétition (moins de valeurs distinctes que d'observations) écarte
            # les colonnes d'identifiants/texte libre sans dépendre du nom.
            if 2 <= len(unique) <= min(20, len(non_null)) and len(unique) < len(non_null):
                return True
        return False

    def _has_regression_target(self, rows: Sequence[Mapping[str, Any]]) -> bool:
        if not self._has_numeric_feature(rows):
            return False

        for row in rows:
            for key, value in row.items():
                lowered = str(key).lower()
                if lowered in {"price", "cost", "revenue", "sales", "amount", "value", "total", "margin"}:
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        return True

        for column in self._candidate_target_columns(rows):
            values = [row.get(column) for row in rows if column in row]
            numeric = [value for value in values if isinstance(value, (int, float)) and not isinstance(value, bool)]
            # >= 3 valeurs distinctes : écarte les indicateurs binaires (0/1),
            # déjà couverts par la classification, pour ne pas les compter deux fois.
            if len(numeric) >= max(2, len(values) // 2) and len(set(numeric)) >= 3:
                return True
        return False

    def _has_segmentation_signal(self, rows: Sequence[Mapping[str, Any]]) -> bool:
        numeric_keys = {
            str(key).lower()
            for row in rows
            for key, value in row.items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        }

        segmentation_indicators = {
            "frequency",
            "monetary_value",
            "recency",
            "age",
            "income",
            "tenure",
            "engagement_score",
            "lifetime_value",
        }

        return bool(segmentation_indicators.intersection(numeric_keys)) or (
            len(numeric_keys) >= 4 and bool({"customer_id", "user_id", "client_id", "customer"}.intersection(numeric_keys))
        )

    def _has_recommendation_signal(self, rows: Sequence[Mapping[str, Any]]) -> bool:
        # Phase 22 : alias élargis pour couvrir les noms de colonnes réels
        # observés chez différentes entreprises (ex. "client_number"/"sku"/
        # "units" vs. "customer_id"/"product_code"/"quantity") — même
        # principe de détection, jamais de colonne inventée.
        has_customer = any(
            any(
                key.lower() in {"customer_id", "user_id", "client_id", "user", "customer", "client_number", "buyer_id"}
                for key in row
            )
            for row in rows
        )
        has_product = any(
            any(
                key.lower() in {"product_id", "item_id", "sku", "product", "item", "product_code", "article_id"}
                for key in row
            )
            for row in rows
        )
        has_interaction = any(
            any(
                key.lower() in {"interaction", "rating", "score", "click", "purchase", "quantity", "units", "order_id"}
                for key in row
            )
            for row in rows
        )
        return has_customer and has_product and has_interaction

    def _has_anomaly_signal(self, rows: Sequence[Mapping[str, Any]]) -> bool:
        numeric = self._collect_numeric_values(rows)
        normalized_numeric = {str(key).lower(): count for key, count in numeric.items()}
        has_time_column = any(str(key).lower() in {"date", "time", "datetime", "timestamp"} for row in rows for key in row)
        return has_time_column and len(normalized_numeric) >= 2 and any(
            key in {"amount", "quantity", "duration", "latency", "response_time", "error_rate"}
            for key in normalized_numeric
        )

    def _has_sentiment_signal(self, rows: Sequence[Mapping[str, Any]]) -> bool:
        text_candidates = {
            key.lower()
            for row in rows
            for key, value in row.items()
            if isinstance(value, str) and ("text" in key.lower() or "comment" in key.lower() or "review" in key.lower())
        }
        return bool(text_candidates)

    def _candidate_target_columns(self, rows: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
        keys = set()
        for row in rows:
            for key in row:
                lowered = str(key).lower()
                # "y" est vérifié en égalité stricte (convention ML : colonne
                # cible littéralement nommée "y") et jamais en sous-chaîne,
                # sinon toute colonne contenant la lettre "y" (ex. "quantity")
                # ferait à tort disparaître le repli générique ci-dessous.
                if lowered == "y" or any(
                    token in lowered
                    for token in ("target", "label", "class", "status", "churn", "risk", "sentiment", "outcome")
                ):
                    keys.add(key)
        if keys:
            return tuple(sorted(keys))

        # Repli générique : aucune colonne détectée par nom -> on considère
        # toute colonne non identifiante/texte libre dont les valeurs se
        # répètent réellement entre les lignes (signal indépendant du nom,
        # ex. "segment"/"is_bad_review" sans alias explicite).
        excluded_names = {"id", "date", "time", "timestamp", "name", "text", "comment", "description"}
        all_keys = {key for row in rows for key in row}
        fallback_keys = set()
        for key in all_keys:
            lowered = str(key).lower()
            if lowered in excluded_names or lowered.endswith("_id"):
                continue
            if any(token in lowered for token in ("text", "comment", "description")):
                continue
            values = [row.get(key) for row in rows if key in row]
            non_null = [value for value in values if value is not None]
            if not non_null:
                continue
            unique = {str(value) for value in non_null}
            if len(unique) < len(non_null):
                fallback_keys.add(key)
        return tuple(sorted(fallback_keys))

    def _collect_numeric_values(self, rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in rows:
            for key, value in row.items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    counts[str(key)] = counts.get(str(key), 0) + 1
        return counts

    def _has_numeric_feature(self, rows: Sequence[Mapping[str, Any]]) -> bool:
        numeric_columns = {
            str(key).lower()
            for row in rows
            for key, value in row.items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
            and str(key).lower() not in {"id", "date", "time", "timestamp"}
        }
        return len(numeric_columns) >= 2

    def _normalize_module_task(self, task_code: str) -> str:
        code = str(task_code).lower()
        if "forecast" in code or code in {"demand", "cash_flow", "financial_forecast"}:
            return "forecasting"
        if "price" in code:
            return "regression"
        if "segment" in code or code == "segmentation":
            return "segmentation"
        if "recommend" in code:
            return "recommendation"
        if "sentiment" in code:
            return "sentiment_analysis"
        if "anomaly" in code:
            return "anomaly_detection"
        if any(token in code for token in ("bad_review", "churn", "lead", "classif", "email_classification")):
            return "classification"
        if code in {"demand", "weekly_forecast"}:
            return "forecasting"
        return code
