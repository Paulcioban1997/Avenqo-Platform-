"""`CapabilityDatasetAdapter` — Phase 27.

Responsabilité unique : transformer un `PreparedCompanyDataset` (Phase 26) en
`CapabilityDataset` pour UNE capacité métier, en validant la compatibilité
AVANT toute utilisation par un moteur ML. N'entraîne jamais de modèle, ne
sélectionne jamais un algorithme, ne fait aucune feature engineering : ceci
reste la responsabilité des capacités RetailSenseAI en aval (voir
`shared/ai_engine/capability_dataset/feature_engineering.py` pour la
frontière canonical data -> derived features).
"""

from __future__ import annotations

from shared.ai_engine.capability_dataset.contracts import (
    CapabilityDataset,
    CapabilityDatasetValidation,
)
from shared.ai_engine.capability_dataset.exceptions import (
    InvalidCapabilityDataset,
    MissingCapabilityFields,
    UnknownCapability,
    capability_label,
    field_labels,
)
from shared.ai_engine.dataset_ingestion.capability_requirements import CAPABILITY_DATA_REQUIREMENTS
from shared.ai_engine.dataset_ingestion.prepared_dataset import PreparedCompanyDataset

ADAPTER_VERSION = "1.0"


def _reverse_mapping(canonical_columns: dict[str, str]) -> dict[str, str]:
    """canonical_field -> original_column (inverse de `canonical_columns`)."""

    return {canonical: original for original, canonical in canonical_columns.items()}


def _has_value(row: dict[str, object], original_column: str | None) -> bool:
    if original_column is None or original_column not in row:
        return False
    value = row[original_column]
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return True


class CapabilityDatasetAdapter:
    """Adapte `PreparedCompanyDataset` -> `CapabilityDataset` par capacité."""

    def validate(
        self,
        prepared: PreparedCompanyDataset,
        capability: str,
    ) -> CapabilityDatasetValidation:
        """Vérifie la compatibilité sans jamais lever d'exception métier.

        Utilisé par la readiness API et par `prepare()` avant de construire
        le `CapabilityDataset` définitif.
        """

        if capability not in CAPABILITY_DATA_REQUIREMENTS:
            raise UnknownCapability(f"Unknown capability: '{capability}'.")

        required_fields = CAPABILITY_DATA_REQUIREMENTS[capability]
        available_fields = set(prepared.canonical_columns.values())
        missing_fields = tuple(field for field in required_fields if field not in available_fields)

        usable_row_count = 0
        if not missing_fields:
            reverse = _reverse_mapping(prepared.canonical_columns)
            required_originals = [reverse.get(field) for field in required_fields]
            usable_row_count = sum(
                1
                for row in prepared.rows
                if all(_has_value(row, original) for original in required_originals)
            )

        warnings: tuple[str, ...] = ()
        if missing_fields:
            warnings = (
                f"{capability_label(capability)} requires {field_labels(missing_fields)}.",
            )
        elif usable_row_count == 0:
            warnings = (
                f"{capability_label(capability)} has no usable rows for the "
                "data currently available.",
            )

        return CapabilityDatasetValidation(
            capability=capability,
            ready=not missing_fields and usable_row_count > 0,
            missing_fields=missing_fields,
            invalid_fields=(),
            warnings=warnings,
            row_count=len(prepared.rows),
            usable_row_count=usable_row_count,
        )

    def prepare(
        self,
        prepared: PreparedCompanyDataset,
        capability: str,
    ) -> CapabilityDataset:
        """Construit le `CapabilityDataset` officiel pour `capability`.

        Lève `MissingCapabilityFields`/`InvalidCapabilityDataset` (business
        exceptions, jamais une erreur pandas/sklearn) si les données ne
        permettent pas d'exécuter la capacité demandée.
        """

        validation = self.validate(prepared, capability)
        if validation.missing_fields:
            raise MissingCapabilityFields(capability, validation.missing_fields)
        if validation.usable_row_count == 0:
            raise InvalidCapabilityDataset(capability)

        return CapabilityDataset(
            company_id=prepared.company_id,
            dataset_id=prepared.dataset_id,
            dataset_version=prepared.version,
            capability=capability,
            required_fields=CAPABILITY_DATA_REQUIREMENTS[capability],
            available_fields=tuple(sorted(set(prepared.canonical_columns.values()))),
            canonical_columns=prepared.canonical_columns,
            rows=prepared.rows,
            row_count=len(prepared.rows),
            warnings=validation.warnings,
            adapter_version=ADAPTER_VERSION,
        )
