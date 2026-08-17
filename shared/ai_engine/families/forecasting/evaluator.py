"""Évaluation des candidats Forecasting : délègue au service d'évaluation partagé."""

from shared.ai_engine.core.evaluator import Evaluator


class ForecastingEvaluator(Evaluator):
    """Point d'extension pour des métriques Forecasting dédiées (ex : RMSE, MAPE)."""
