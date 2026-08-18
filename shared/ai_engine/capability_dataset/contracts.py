"""Contrats de données Phase 27 : `CapabilityDataset` et sa validation.

`CapabilityDataset` représente les données canoniques nécessaires à UNE
capacité métier RetailSenseAI, dérivées d'un `PreparedCompanyDataset`
(Phase 26). Il ne copie jamais les lignes : `rows` référence directement le
tuple immuable du `PreparedCompanyDataset` d'origine.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class CapabilityDatasetValidation:
    """Résultat structuré, non levant, de la vérification de compatibilité.

    Permet de détecter une incompatibilité AVANT tout appel pandas/sklearn
    (voir `CapabilityDatasetAdapter.validate`).
    """

    capability: str
    ready: bool
    missing_fields: tuple[str, ...]
    invalid_fields: tuple[str, ...]
    warnings: tuple[str, ...]
    row_count: int
    usable_row_count: int


@dataclass(frozen=True, slots=True)
class CapabilityDataset:
    """Entrée canonique d'UNE capacité métier, prête pour feature engineering.

    `rows` reste au format `PreparedCompanyDataset.rows` (clés = colonnes
    originales du client) ; `canonical_columns` permet de résoudre chaque
    champ canonique requis vers sa colonne originale sans dupliquer les
    données.
    """

    company_id: UUID
    dataset_id: UUID
    dataset_version: int
    capability: str
    required_fields: tuple[str, ...]
    available_fields: tuple[str, ...]
    canonical_columns: dict[str, str]
    rows: tuple[dict[str, object], ...]
    row_count: int
    warnings: tuple[str, ...]
    mapping_version: int | None = None
    cleaning_version: str | None = None
    adapter_version: str = "1.0"
