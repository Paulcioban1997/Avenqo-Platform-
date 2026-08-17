"""Évaluation des candidats Vision : délègue au service d'évaluation partagé."""

from shared.ai_engine.core.evaluator import Evaluator


class VisionEvaluator(Evaluator):
    """Point d'extension pour des métriques Vision dédiées (ex : top-1 accuracy, mAP)."""
