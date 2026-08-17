"""Évaluation des candidats Anomaly Detection : délègue au service d'évaluation partagé."""

from shared.ai_engine.core.evaluator import Evaluator


class AnomalyDetectionEvaluator(Evaluator):
    """Point d'extension pour des métriques Anomaly Detection dédiées (ex : precision@k, AUC-ROC)."""
