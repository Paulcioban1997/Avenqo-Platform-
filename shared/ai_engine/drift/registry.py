"""Registre de sélection des tests statistiques (interne, sans rapport avec
`shared.ai_engine.registry.registry.ModelRegistry`).

Décide QUELS tests statistiques exécuter selon le type de variable — jamais
tous les tests systématiquement (voir cahier des charges Phase 7). Ajouter une
nouvelle méthode statistique ne nécessite qu'une entrée ici : aucune autre
partie de `data_drift.py`/`prediction_drift.py` n'a besoin d'être modifiée.
"""

from __future__ import annotations

from typing import Literal

DriftVariableKind = Literal["numerical", "categorical"]

# Numérique continu : PSI (décision, seuils Enterprise universels) + KS
# (significativité statistique) + Wasserstein (amplitude, informationnel).
NUMERICAL_TESTS: tuple[str, ...] = ("psi", "ks", "wasserstein")

# Catégoriel : PSI (décision) + Chi carré (significativité) + Jensen-Shannon
# (magnitude bornée/symétrique, particulièrement adaptée aux scores/prédictions).
CATEGORICAL_TESTS: tuple[str, ...] = ("psi", "chi_square", "jensen_shannon")

# KL Divergence : jamais utilisée par défaut (asymétrique, non bornée) — seulement
# activée explicitement pour le prediction drift catégoriel (voir prediction_drift.py),
# où comparer des distributions de scores/classes prédites est son usage classique.
OPTIONAL_KL_DIVERGENCE = "kl_divergence"


def select_statistical_tests(kind: DriftVariableKind, include_kl_divergence: bool = False) -> tuple[str, ...]:
    """Retourne les tests à exécuter pour une variable de ce type."""

    tests = NUMERICAL_TESTS if kind == "numerical" else CATEGORICAL_TESTS
    if include_kl_divergence and kind == "categorical":
        return (*tests, OPTIONAL_KL_DIVERGENCE)
    return tests

