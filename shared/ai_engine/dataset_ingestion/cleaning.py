"""Nettoyage générique et non destructif d'un dataset d'entreprise (Phase 26).

Règles absolues : ne jamais supprimer massivement des lignes sans trace, ne
jamais inventer/imputer une valeur métier, ne jamais transformer tous les
outliers automatiquement. Seules les duplications EXACTES de lignes sont
supprimées, et chaque conversion est comptabilisée dans le `CleaningReport`.
"""

from __future__ import annotations

from datetime import datetime, timezone
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from shared.ai_engine.dataset_ingestion.canonical_fields import CANONICAL_FIELD_SEMANTIC_TYPE
from shared.ai_engine.dataset_ingestion.type_inference import SemanticType, infer_semantic_type
from shared.ai_engine.dataset_ingestion.date_parsing import infer_date_order, parse_date

_CURRENCY_SYMBOLS = re.compile(r"[$€£CADUS\s]", re.IGNORECASE)
_BOOLEAN_TRUE = {"true", "yes", "y", "1", "vrai", "oui"}
_BOOLEAN_FALSE = {"false", "no", "n", "0", "faux", "non"}


@dataclass(frozen=True, slots=True)
class CellModification:
    row_index: int
    row_id: str
    entity: str
    column: str
    before: Any
    after: Any
    reason: str
    rule: str
    category: str
    timestamp: str
    source: str = ""
    diff: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "row_index": self.row_index,
            "row_id": self.row_id,
            "entity": self.entity,
            "column": self.column,
            "before": self.before,
            "after": self.after,
            "reason": self.reason,
            "rule": self.rule,
            "category": self.category,
            "timestamp": self.timestamp,
            "source": self.source,
            "diff": self.diff,
        }


@dataclass(frozen=True, slots=True)
class ColumnCleaningReport:
    column_name: str
    canonical_field: str | None
    semantic_type: str
    missing_values_detected: int
    missing_values_corrected: int
    invalid_values_detected: int
    invalid_values_corrected: int
    numeric_conversions: int
    date_conversions: int
    boolean_conversions: int
    original_name: str = ""
    original_type: str = "text"
    final_type: str = ""
    modified_count: int = 0
    error_count: int = 0
    quality_score: float = 100.0
    samples: tuple[dict[str, Any], ...] = ()
    sample_modifications: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "column_name": self.column_name,
            "original_name": self.original_name or self.column_name,
            "canonical_field": self.canonical_field,
            "semantic_type": self.semantic_type,
            "original_type": self.original_type,
            "final_type": self.final_type or self.semantic_type,
            "null_count_before": self.missing_values_detected,
            "null_count_after": max(
                0, self.missing_values_detected - self.missing_values_corrected
            ),
            "missing_values_detected": self.missing_values_detected,
            "missing_values_corrected": self.missing_values_corrected,
            "invalid_values_detected": self.invalid_values_detected,
            "invalid_values_corrected": self.invalid_values_corrected,
            "numeric_conversions": self.numeric_conversions,
            "date_conversions": self.date_conversions,
            "boolean_conversions": self.boolean_conversions,
            "modified_count": self.modified_count,
            "error_count": self.error_count or self.invalid_values_detected,
            "quality_score": round(self.quality_score, 1),
            "samples": list(self.samples),
            "sample_modifications": list(self.sample_modifications),
        }


@dataclass(frozen=True, slots=True)
class CleaningReport:
    rows_before: int
    rows_after: int
    duplicates_removed: int
    numeric_conversions: int
    date_conversions: int
    null_cells_detected: int
    invalid_rows: int
    boolean_conversions: int = 0
    invalid_values_detected: int = 0
    invalid_values_corrected: int = 0
    column_reports: tuple[ColumnCleaningReport, ...] = ()
    column_count: int = 0
    modifications: tuple[CellModification, ...] = ()
    quality_score: float = 100.0


class CompanyDatasetCleaner:
    """Nettoie un dataset de manière générique, avec ou sans mapping préalable."""

    def clean(
        self,
        rows: Sequence[Mapping[str, Any]],
        mapping: Mapping[str, str] | None = None,
        source_name: str = "Dataset",
    ) -> tuple[tuple[dict[str, Any], ...], CleaningReport]:
        rows_before = len(rows)
        if not rows:
            return (), CleaningReport(
                rows_before=0,
                rows_after=0,
                duplicates_removed=0,
                numeric_conversions=0,
                date_conversions=0,
                null_cells_detected=0,
                invalid_rows=0,
            )

        active_mapping = dict(mapping or {})
        now_iso = datetime.now(timezone.utc).isoformat()

        # 1. Normalisation des en-têtes et trim initial des lignes
        trimmed_rows: list[dict[str, Any]] = []
        original_to_cleaned_col: dict[str, str] = {}
        for row in rows:
            trimmed_row: dict[str, Any] = {}
            for col_key, val in row.items():
                col_clean = str(col_key).strip()
                original_to_cleaned_col.setdefault(col_clean, str(col_key))
                trimmed_row[col_clean] = val
            trimmed_rows.append(trimmed_row)

        # 2. Déduplication exacte
        deduplicated, duplicates_removed = self._drop_exact_duplicates(trimmed_rows)

        # 3. Inférence dynamique des types pour CHAQUE colonne présente
        all_columns = sorted(
            list({col for r in deduplicated for col in r.keys()}),
            key=lambda c: (
                0 if any(k in c.lower() for k in ("name", "title", "product", "sku", "price", "stock", "quantity", "order", "status")) else 1,
                c.lower(),
            ),
        )

        inferred_types: dict[str, list[SemanticType]] = {}
        date_orders: dict[str, Any] = {}
        for col in all_columns:
            canonical_field = active_mapping.get(col)
            expected: list[SemanticType] = []
            if canonical_field is not None and canonical_field in CANONICAL_FIELD_SEMANTIC_TYPE:
                expected = list(CANONICAL_FIELD_SEMANTIC_TYPE[canonical_field])
            if not expected:
                col_values = [r.get(col) for r in deduplicated if r.get(col) is not None]
                inferred = infer_semantic_type(col, col_values)
                expected = [inferred]
            inferred_types[col] = expected
            if SemanticType.DATETIME in expected:
                date_orders[col] = infer_date_order(r.get(col) for r in deduplicated)

        # 4. Traitement cellule par cellule avec journalisation fine des modifications
        numeric_conversions = 0
        date_conversions = 0
        boolean_conversions = 0
        null_cells_detected = 0
        invalid_values_detected = 0
        invalid_values_corrected = 0
        invalid_row_flags: list[bool] = []
        column_stats: dict[str, dict[str, Any]] = {}
        modifications: list[CellModification] = []

        cleaned_rows: list[dict[str, Any]] = []
        for row_idx, row in enumerate(deduplicated):
            cleaned_row = dict(row)
            row_invalid = False

            # Résolution de l'identifiant et de l'entité
            row_id = str(
                cleaned_row.get("id")
                or cleaned_row.get("product_id")
                or cleaned_row.get("order_id")
                or cleaned_row.get("sku")
                or cleaned_row.get("source_record_id")
                or f"#{row_idx + 1}"
            )
            entity = str(
                cleaned_row.get("product_name")
                or cleaned_row.get("name")
                or cleaned_row.get("title")
                or cleaned_row.get("order_id")
                or f"Row {row_idx + 1}"
            )

            for col in all_columns:
                stats = column_stats.setdefault(
                    col,
                    self._new_column_stats(
                        column_name=col,
                        original_name=original_to_cleaned_col.get(col, col),
                        canonical_field=active_mapping.get(col),
                        expected_types=inferred_types.get(col, ()),
                    ),
                )
                val = cleaned_row.get(col)

                # Null & empty string detection
                if val is None or (isinstance(val, str) and val.strip() == ""):
                    stats["missing_values_detected"] += 1
                    null_cells_detected += 1
                    if val == "":
                        cleaned_row[col] = None
                        modifications.append(
                            CellModification(
                                row_index=row_idx,
                                row_id=row_id,
                                entity=entity,
                                column=col,
                                before='""',
                                after="null",
                                reason="Chaîne vide convertie en valeur nulle",
                                rule="Normalisation valeur nulle",
                                category="normalized",
                                timestamp=now_iso,
                                source=source_name,
                            )
                        )
                    continue

                orig_val = val
                expected = inferred_types.get(col, [])

                # Trim & normalisation Unicode des chaînes
                if isinstance(val, str):
                    norm = unicodedata.normalize("NFKC", val).strip()
                    if norm != val:
                        val = norm
                        cleaned_row[col] = val
                        stats["modified_count"] += 1
                        modifications.append(
                            CellModification(
                                row_index=row_idx,
                                row_id=row_id,
                                entity=entity,
                                column=col,
                                before=repr(orig_val),
                                after=repr(val),
                                reason="Espaces superflus nettoyés et normalisation Unicode",
                                rule="Trim & Unicode",
                                category="normalized",
                                timestamp=now_iso,
                                source=source_name,
                            )
                        )

                # Conversion Datetime
                if SemanticType.DATETIME in expected:
                    converted, ok = parse_date(val, date_orders.get(col))
                    if ok and str(converted) != str(orig_val):
                        date_conversions += 1
                        stats["date_conversions"] += 1
                        stats["modified_count"] += 1
                        cleaned_row[col] = converted
                        modifications.append(
                            CellModification(
                                row_index=row_idx,
                                row_id=row_id,
                                entity=entity,
                                column=col,
                                before=str(orig_val),
                                after=str(converted),
                                reason="Standardisation du format de date ISO",
                                rule="Conversion Date",
                                category="converted",
                                timestamp=now_iso,
                                source=source_name,
                            )
                        )
                    elif not ok:
                        row_invalid = True
                        invalid_values_detected += 1
                        stats["invalid_values_detected"] += 1
                        cleaned_row[col] = val

                # Conversion Numérique (Float, Integer, Currency, Percentage)
                elif any(
                    t in expected
                    for t in (
                        SemanticType.CURRENCY,
                        SemanticType.FLOAT,
                        SemanticType.INTEGER,
                        SemanticType.PERCENTAGE,
                        SemanticType.DECIMAL,
                    )
                ):
                    converted, ok = self._convert_numeric(val)
                    if ok and converted != orig_val and str(converted) != str(orig_val):
                        numeric_conversions += 1
                        stats["numeric_conversions"] += 1
                        stats["modified_count"] += 1
                        cleaned_row[col] = converted
                        diff_badge = ""
                        if isinstance(orig_val, (int, float)) and isinstance(converted, (int, float)):
                            delta = converted - orig_val
                            diff_badge = f"+{delta}" if delta > 0 else str(delta)
                        modifications.append(
                            CellModification(
                                row_index=row_idx,
                                row_id=row_id,
                                entity=entity,
                                column=col,
                                before=str(orig_val),
                                after=str(converted),
                                reason="Conversion de texte en valeur numérique typée",
                                rule="Conversion Numérique",
                                category="converted",
                                timestamp=now_iso,
                                source=source_name,
                                diff=diff_badge,
                            )
                        )
                    elif not ok:
                        row_invalid = True
                        invalid_values_detected += 1
                        stats["invalid_values_detected"] += 1
                        cleaned_row[col] = val

                # Conversion Booléen
                elif SemanticType.BOOLEAN in expected:
                    converted, changed = self._convert_boolean(val)
                    if changed:
                        boolean_conversions += 1
                        stats["boolean_conversions"] += 1
                        stats["modified_count"] += 1
                        cleaned_row[col] = converted
                        modifications.append(
                            CellModification(
                                row_index=row_idx,
                                row_id=row_id,
                                entity=entity,
                                column=col,
                                before=str(orig_val),
                                after=str(converted),
                                reason="Standardisation du format booléen",
                                rule="Normalisation Booléen",
                                category="normalized",
                                timestamp=now_iso,
                                source=source_name,
                            )
                        )

            # Vérification des valeurs aberrantes flottantes (NaN, Inf)
            for col, val in list(cleaned_row.items()):
                if val is not None and isinstance(val, float) and (val != val or val in (float("inf"), float("-inf"))):
                    row_invalid = True
                    invalid_values_detected += 1
                    invalid_values_corrected += 1
                    stats = column_stats[col]
                    stats["invalid_values_detected"] += 1
                    stats["invalid_values_corrected"] += 1
                    stats["modified_count"] += 1
                    cleaned_row[col] = None
                    modifications.append(
                        CellModification(
                            row_index=row_idx,
                            row_id=row_id,
                            entity=entity,
                            column=col,
                            before=str(val),
                            after="null",
                            reason="Remplacement valeur flottante invalide (NaN/Inf)",
                            rule="Correction Flottant Invalide",
                            category="changed",
                            timestamp=now_iso,
                            source=source_name,
                        )
                    )

            invalid_row_flags.append(row_invalid)
            cleaned_rows.append(cleaned_row)

        # 5. Synthèse par colonne & Score Qualité
        total_rows_after = len(cleaned_rows)
        column_reports_list: list[ColumnCleaningReport] = []
        for col_name in sorted(column_stats.keys()):
            cdata = dict(column_stats[col_name])
            missing_det = cdata["missing_values_detected"]
            inv_det = cdata["invalid_values_detected"]
            # Calcul du score qualité par colonne (0 à 100%)
            col_quality = 100.0
            if total_rows_after > 0:
                missing_pen = (missing_det / total_rows_after) * 35.0
                inv_pen = (inv_det / total_rows_after) * 65.0
                col_quality = max(0.0, min(100.0, 100.0 - missing_pen - inv_pen))

            # Exemples de modifications pour cette colonne
            col_samples: list[dict[str, Any]] = [
                {"before": m.before, "after": m.after, "rule": m.rule}
                for m in modifications
                if m.column == col_name
            ][:3]

            cdata["quality_score"] = col_quality
            cdata["samples"] = tuple(col_samples)
            column_reports_list.append(ColumnCleaningReport(**cdata))

        # Score global du dataset
        overall_quality = (
            sum(cr.quality_score for cr in column_reports_list) / len(column_reports_list)
            if column_reports_list
            else 100.0
        )
        if duplicates_removed > 0 and rows_before > 0:
            dup_pen = min(15.0, (duplicates_removed / rows_before) * 50.0)
            overall_quality = max(0.0, overall_quality - dup_pen)

        return tuple(cleaned_rows), CleaningReport(
            rows_before=rows_before,
            rows_after=len(cleaned_rows),
            duplicates_removed=duplicates_removed,
            numeric_conversions=numeric_conversions,
            date_conversions=date_conversions,
            null_cells_detected=null_cells_detected,
            invalid_rows=sum(invalid_row_flags),
            boolean_conversions=boolean_conversions,
            invalid_values_detected=invalid_values_detected,
            invalid_values_corrected=invalid_values_corrected,
            column_reports=tuple(column_reports_list),
            column_count=len(column_reports_list),
            modifications=tuple(modifications),
            quality_score=round(overall_quality, 1),
        )

    @staticmethod
    def _drop_exact_duplicates(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
        seen: set[str] = set()
        unique_rows: list[dict[str, Any]] = []
        duplicates = 0
        for row in rows:
            fingerprint = repr(sorted(row.items()))
            if fingerprint in seen:
                duplicates += 1
                continue
            seen.add(fingerprint)
            unique_rows.append(row)
        return unique_rows, duplicates

    @staticmethod
    def _convert_numeric(value: Any) -> tuple[Any, bool]:
        if value is None:
            return None, True
        if isinstance(value, bool):
            return value, False
        if isinstance(value, (int, float)):
            return value, True
        if isinstance(value, str):
            cleaned = _CURRENCY_SYMBOLS.sub("", value).rstrip("%").strip()
            if not cleaned:
                return value, False
            if "," in cleaned and "." in cleaned:
                if cleaned.rfind(",") > cleaned.rfind("."):
                    cleaned = cleaned.replace(".", "").replace(",", ".")
                else:
                    cleaned = cleaned.replace(",", "")
            elif "," in cleaned:
                parts = cleaned.split(",")
                if len(parts) == 2 and len(parts[1]) in {1, 2}:
                    cleaned = ".".join(parts)
                elif all(len(part) == 3 for part in parts[1:]):
                    cleaned = "".join(parts)
                else:
                    return value, False
            try:
                number = float(cleaned)
                return (int(number) if number.is_integer() else number), True
            except ValueError:
                return value, False
        return value, False

    @staticmethod
    def _convert_boolean(value: Any) -> tuple[Any, bool]:
        if value is None or isinstance(value, bool):
            return value, False
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in _BOOLEAN_TRUE:
                return True, True
            if lowered in _BOOLEAN_FALSE:
                return False, True
        return value, False

    @staticmethod
    def _new_column_stats(
        column_name: str,
        original_name: str,
        canonical_field: str | None,
        expected_types: Sequence[SemanticType],
    ) -> dict[str, Any]:
        semantic_type = "text"
        original_type = "text"
        if SemanticType.DATETIME in expected_types:
            semantic_type = "datetime"
            original_type = "datetime"
        elif any(
            t in expected_types
            for t in (
                SemanticType.CURRENCY,
                SemanticType.FLOAT,
                SemanticType.INTEGER,
                SemanticType.PERCENTAGE,
                SemanticType.DECIMAL,
            )
        ):
            semantic_type = "numeric"
            original_type = "number"
        elif SemanticType.BOOLEAN in expected_types:
            semantic_type = "boolean"
            original_type = "boolean"
        elif any(t in expected_types for t in (SemanticType.EMAIL, SemanticType.URL, SemanticType.PHONE)):
            semantic_type = "contact"
            original_type = "text"

        return {
            "column_name": column_name,
            "original_name": original_name,
            "canonical_field": canonical_field,
            "semantic_type": semantic_type,
            "original_type": original_type,
            "missing_values_detected": 0,
            "missing_values_corrected": 0,
            "invalid_values_detected": 0,
            "invalid_values_corrected": 0,
            "numeric_conversions": 0,
            "date_conversions": 0,
            "boolean_conversions": 0,
            "modified_count": 0,
            "quality_score": 100.0,
            "samples": (),
        }
