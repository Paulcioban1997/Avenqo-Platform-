"""Score/statut de qualité en langage métier (Phase 26).

Volontairement conservateur : un statut discret (GOOD/WARNING/POOR) avec des
raisons explicites est préféré à un pourcentage précis mais non fondé.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from shared.ai_engine.dataset_ingestion.cleaning import CleaningReport


class DataQualityStatus(str, Enum):
    GOOD = "good"
    WARNING = "warning"
    POOR = "poor"


@dataclass(frozen=True, slots=True)
class DataQualityAssessment:
    status: DataQualityStatus
    reasons: tuple[str, ...]


def assess_quality(cleaning_report: CleaningReport) -> DataQualityAssessment:
    reasons: list[str] = []

    if cleaning_report.rows_after == 0:
        return DataQualityAssessment(
            status=DataQualityStatus.POOR,
            reasons=("Aucune ligne exploitable après nettoyage.",),
        )

    invalid_ratio = cleaning_report.invalid_rows / cleaning_report.rows_after
    total_cells = max(cleaning_report.rows_after, 1)
    null_ratio = cleaning_report.null_cells_detected / total_cells

    if cleaning_report.rows_after < 3:
        reasons.append("Trop peu de lignes pour une évaluation fiable.")
    if invalid_ratio > 0.3:
        reasons.append("Plus de 30% des lignes contiennent des valeurs invalides.")
    if null_ratio > 3.0:
        reasons.append("Volume de cellules manquantes très élevé.")
    if cleaning_report.duplicates_removed > 0:
        reasons.append(f"{cleaning_report.duplicates_removed} ligne(s) dupliquée(s) supprimée(s).")

    if cleaning_report.rows_after < 3 or invalid_ratio > 0.3 or null_ratio > 3.0:
        status = DataQualityStatus.POOR
    elif reasons or invalid_ratio > 0 or null_ratio > 1.0:
        status = DataQualityStatus.WARNING
        if not reasons:
            reasons.append("Quelques valeurs manquantes ou invalides détectées.")
    else:
        status = DataQualityStatus.GOOD
        reasons.append("Aucune anomalie significative détectée.")

    return DataQualityAssessment(status=status, reasons=tuple(reasons))
