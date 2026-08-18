"""Phase 27 — Capability Dataset layer.

Frontière entre `PreparedCompanyDataset` (Phase 26, données canoniques
d'entreprise) et les capacités métier RetailSenseAI. Aucune capacité ne doit
consommer un `PreparedCompanyDataset` directement : elle reçoit toujours un
`CapabilityDataset` construit par `CapabilityDatasetAdapter`.
"""

from shared.ai_engine.capability_dataset.contracts import (
    CapabilityDataset,
    CapabilityDatasetValidation,
)
from shared.ai_engine.capability_dataset.exceptions import (
    CapabilityDatasetError,
    CapabilityNotReady,
    InvalidCapabilityDataset,
    MissingCapabilityFields,
    UnknownCapability,
)
from shared.ai_engine.capability_dataset.adapter import CapabilityDatasetAdapter

__all__ = [
    "CapabilityDataset",
    "CapabilityDatasetValidation",
    "CapabilityDatasetAdapter",
    "CapabilityDatasetError",
    "CapabilityNotReady",
    "MissingCapabilityFields",
    "InvalidCapabilityDataset",
    "UnknownCapability",
]
