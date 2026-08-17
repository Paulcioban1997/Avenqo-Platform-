"""Sélection de la métrique de comparaison par famille de tâche.

Comme `explainability/registry.py` (Phase 6, sélection de méthode d'explication
par famille) et `drift/registry.py` (Phase 7, sélection de tests statistiques
par type de variable) : ce module n'est **pas** le `ModelRegistry` de stockage
de modèles (`shared.ai_engine.registry.registry.ModelRegistry`) — la
similitude de nom est volontaire et suit la même convention établie.

Portée volontairement plus large que `drift/concept_drift.py::_PRIMARY_METRIC`
(qui ne couvre que classification/régression, seules familles câblées avec une
baseline aujourd'hui) : la comparaison obligatoire de la Phase 8 doit rester
compatible avec le clustering (déjà câblé) et le forecasting/deep learning
(pas encore câblés dans `training_dispatcher.py`, mais déjà présents dans
`shared.ai_engine.training.service.TrainingService`) — deux mappings distincts,
à portées différentes, pas une duplication.
"""

from __future__ import annotations

from typing import Mapping

# (nom de la métrique primaire, "plus haut = meilleur" ?)
_PRIMARY_METRIC_BY_FAMILY: Mapping[str, tuple[str, bool]] = {
    "classification": ("accuracy", True),
    "regression": ("r2", True),
    "clustering": ("silhouette", True),
    # Familles pas encore câblées automatiquement (voir
    # `modules/retailsense/training_specs.py`) : entrées prêtes pour rester
    # compatible dès leur câblage, sans modification de ce registre.
    "forecasting": ("r2", True),
    "deep_learning": ("accuracy", True),
}

# Repli neutre pour toute famille inconnue (jamais d'exception ici).
_DEFAULT_PRIMARY_METRIC: tuple[str, bool] = ("accuracy", True)


def primary_metric_for(family: str) -> tuple[str, bool]:
    """Retourne (nom de métrique, "plus haut = meilleur") pour une famille."""

    return _PRIMARY_METRIC_BY_FAMILY.get(family, _DEFAULT_PRIMARY_METRIC)
