"""Rapport de disponibilité des capacités RetailSenseAI, 100% en langage métier.

Aucune mention de modèle, algorithme ou terme ML : uniquement des noms de
capacités business et des champs manquants exprimés avec le vocabulaire
canonique déjà compréhensible par un utilisateur non technique.
"""

from __future__ import annotations

from dataclasses import dataclass

from shared.ai_engine.dataset_ingestion.capability_requirements import CAPABILITY_DATA_REQUIREMENTS


@dataclass(frozen=True, slots=True)
class CapabilityReadiness:
    capability: str
    ready: bool
    missing_fields: tuple[str, ...]
    warnings: tuple[str, ...]


def assess_capability_readiness(mapped_canonical_fields: set[str]) -> tuple[CapabilityReadiness, ...]:
    reports = []
    for capability, required_fields in CAPABILITY_DATA_REQUIREMENTS.items():
        missing = tuple(field for field in required_fields if field not in mapped_canonical_fields)
        ready = not missing
        warnings: tuple[str, ...] = ()
        if not ready:
            warnings = (
                f"Champs manquants pour activer '{capability}' : {', '.join(missing)}.",
            )
        reports.append(
            CapabilityReadiness(
                capability=capability,
                ready=ready,
                missing_fields=missing,
                warnings=warnings,
            )
        )
    return tuple(reports)
