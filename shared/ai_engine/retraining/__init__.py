"""Auto Retraining Enterprise — décide, seul, quand ré-entraîner un modèle.

Comme les couches Explicabilité (Phase 6) et Drift Detection (Phase 7), ces
objets et concepts (`RetrainingDecision`, règles, comparaison, historique) ne
sont **jamais** exposés à l'utilisateur final : consommés uniquement par le
backend, les tâches internes/admin et les futures phases (Monitoring,
Alerting, AutoML). Aucun bouton "Train"/"Retrain" n'existe côté produit —
cette couche est l'unique décideur autonome, à la manière de Vertex AI Model
Monitoring, SageMaker Model Monitor ou Azure ML Data Drift + Retraining
Pipelines.
"""

from shared.ai_engine.retraining.decision_engine import DecisionEngine
from shared.ai_engine.retraining.service import compare_models, evaluate_retraining, should_activate
from shared.ai_engine.retraining.types import (
    ModelComparisonResult,
    RetrainingDecision,
    RetrainingDecisionResult,
    RetrainingReason,
    RetrainingRulesConfig,
    RetrainingSignals,
    RuleOutcome,
)

__all__ = [
    "DecisionEngine",
    "ModelComparisonResult",
    "RetrainingDecision",
    "RetrainingDecisionResult",
    "RetrainingReason",
    "RetrainingRulesConfig",
    "RetrainingSignals",
    "RuleOutcome",
    "compare_models",
    "evaluate_retraining",
    "should_activate",
]
