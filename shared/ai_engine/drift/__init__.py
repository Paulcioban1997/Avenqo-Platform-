"""Couche de détection de drift (Data/Prediction/Concept/Target) — interne, admin/API uniquement.

Compare, pour chaque modèle actif de `shared.ai_engine.training`, les données
qui arrivent lors d'un nouvel entraînement à une `ReferenceBaseline` figée
lors de l'entraînement de la version précédemment active — sans jamais
ralentir l'entraînement lui-même : la détection ne s'exécute qu'après qu'un
modèle est actif (voir `backend/app/services/training_dispatcher.py`).

Ce module ne doit JAMAIS être importé depuis un chemin visible par
l'utilisateur final : ni les noms des tests statistiques (PSI, KS,
Wasserstein, Chi carré, Jensen-Shannon, KL divergence...) ni les scores bruts
qu'il produit ne doivent apparaître dans une réponse API publique ou une UI.

Point d'entrée public : `service.capture_reference_baseline` / `service.run_drift_check`.
"""

from shared.ai_engine.drift.types import DriftReport, DriftSeverity, ReferenceBaseline

__all__ = ["DriftReport", "DriftSeverity", "ReferenceBaseline"]
