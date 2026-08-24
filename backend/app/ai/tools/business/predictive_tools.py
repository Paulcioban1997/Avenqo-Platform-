"""Outils prédictifs Avenqo — "Avenqo Predictive Intelligence" (Phase 31). READ-ONLY.

Chaque outil consomme un modèle déjà entraîné pour le tenant courant via le
Model Registry existant (`resolve_active_model_type` + `PredictionService`) :
jamais de second moteur de prédiction, jamais de réentraînement pendant une
conversation, jamais de donnée inventée si le modèle/les données manquent.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app.ai.tools.base import ToolArguments
from backend.app.ai.tools.business.predictive_base import PredictiveAITool
from backend.app.ai.tools.contracts import ToolExecutionContext, ToolResult
from backend.app.services.portfolio_decision_service import (
    build_anomaly_signal,
    build_churn_segmentation_signals,
    build_demand_signal,
    build_sales_forecast_signal,
    build_segmentation_signal,
)
from backend.app.services.prediction_runtime import resolve_active_model_type
from shared.ai_engine.prediction.service import PredictionService

RETAIL_MODULE_CODE = "retail"

# Tâches prédictives connues, dans l'ordre exposé par `get_prediction_summary`
# (jamais une liste inventée : ce sont exactement les tâches câblées dans
# `modules/retailsense/training_specs.py::MODULE_TRAINING_SPECS["retail"]`
# qui disposent d'un outil prédictif Phase 31 dédié).
_PREDICTIVE_TASK_CODES: tuple[tuple[str, str], ...] = (
    ("churn", "churn_risk"),
    ("segmentation", "segment_insights"),
    ("demand", "demand_forecast"),
    ("weekly_forecast", "sales_forecast"),
    ("anomaly", "anomalies"),
)


class ChurnRiskArgs(ToolArguments):
    pass


class GetChurnRiskTool(PredictiveAITool):
    name = "get_churn_risk"
    description = (
        "Return how many customers are currently at risk of churn, based on the tenant's "
        "already trained churn model. Never retrains a model; returns unavailable if no "
        "churn model has been trained yet."
    )
    input_schema = ChurnRiskArgs
    required_permissions = ("ai:use",)
    requires_capability = "churn"
    task_type = "churn"

    def __init__(self, session: Session, prediction_service: PredictionService) -> None:
        self._session, self._prediction_service = session, prediction_service

    async def build_prediction(self, context: ToolExecutionContext, arguments: ChurnRiskArgs) -> ToolResult:
        churn_signal, _segmentation_signal = build_churn_segmentation_signals(
            self._session, context.tenant, RETAIL_MODULE_CODE, self._prediction_service
        )
        return ToolResult(
            success=True,
            data={
                "at_risk_customers_count": churn_signal.value,
                "metric": churn_signal.metric,
            },
            metadata={"model_capability": "churn", "task_code": "churn"},
        )


class SegmentInsightsArgs(ToolArguments):
    pass


class GetSegmentInsightsTool(PredictiveAITool):
    name = "get_segment_insights"
    description = (
        "Return the dominant customer segment identified by the tenant's already trained "
        "segmentation model, and its share of the customer portfolio."
    )
    input_schema = SegmentInsightsArgs
    required_permissions = ("ai:use",)
    requires_capability = "segmentation"
    task_type = "segmentation"

    def __init__(self, session: Session, prediction_service: PredictionService) -> None:
        self._session, self._prediction_service = session, prediction_service

    async def build_prediction(self, context: ToolExecutionContext, arguments: SegmentInsightsArgs) -> ToolResult:
        signal = build_segmentation_signal(
            self._session, context.tenant, RETAIL_MODULE_CODE, self._prediction_service
        )
        return ToolResult(
            success=True,
            data={
                "dominant_segment": signal.entity,
                "segment_share": signal.value,
                "metric": signal.metric,
            },
            metadata={"model_capability": "segmentation", "task_code": "segmentation"},
        )


class DemandForecastArgs(ToolArguments):
    pass


class GetDemandForecastTool(PredictiveAITool):
    name = "get_demand_forecast"
    description = (
        "Return the tenant's recent demand trend, based on the already trained demand model, "
        "compared to historical demand."
    )
    input_schema = DemandForecastArgs
    required_permissions = ("ai:use",)
    requires_capability = "demand_forecast"
    task_type = "demand"

    def __init__(self, session: Session, prediction_service: PredictionService) -> None:
        self._session, self._prediction_service = session, prediction_service

    async def build_prediction(self, context: ToolExecutionContext, arguments: DemandForecastArgs) -> ToolResult:
        signal = build_demand_signal(self._session, context.tenant, RETAIL_MODULE_CODE, self._prediction_service)
        return ToolResult(
            success=True,
            data={
                "entity": signal.entity,
                "demand_trend_value": signal.value,
                "direction": signal.direction.value,
            },
            metadata={"model_capability": "demand", "task_code": "demand"},
        )


class SalesForecastArgs(ToolArguments):
    horizon: int | None = None


class GetSalesForecastTool(PredictiveAITool):
    name = "get_sales_forecast"
    description = (
        "Return a sales forecast for the next periods, based on the tenant's already trained "
        "forecasting model. Never trains a new model; the horizon defaults to what the model "
        "was trained for."
    )
    input_schema = SalesForecastArgs
    required_permissions = ("ai:use",)
    requires_capability = "sales_forecast"
    task_type = "weekly_forecast"

    def __init__(self, session: Session, prediction_service: PredictionService) -> None:
        self._session, self._prediction_service = session, prediction_service

    async def build_prediction(self, context: ToolExecutionContext, arguments: SalesForecastArgs) -> ToolResult:
        signal = build_sales_forecast_signal(
            self._session, context.tenant, RETAIL_MODULE_CODE, self._prediction_service, horizon=arguments.horizon
        )
        return ToolResult(
            success=True,
            data={
                "forecast_points": signal.metadata.get("forecast_points"),
                "horizon": signal.metadata.get("horizon"),
                "forecasted_total": signal.value,
            },
            metadata={"model_capability": "forecasting", "task_code": "weekly_forecast"},
        )


class AnomaliesArgs(ToolArguments):
    pass


class GetAnomaliesTool(PredictiveAITool):
    name = "get_anomalies"
    description = (
        "Return how many records look anomalous, based on the tenant's already trained anomaly "
        "detection model. Never invents anomalies; unavailable if no anomaly model exists."
    )
    input_schema = AnomaliesArgs
    required_permissions = ("ai:use",)
    requires_capability = "anomaly_detection"
    task_type = "anomaly"

    def __init__(self, session: Session, prediction_service: PredictionService) -> None:
        self._session, self._prediction_service = session, prediction_service

    async def build_prediction(self, context: ToolExecutionContext, arguments: AnomaliesArgs) -> ToolResult:
        signal = build_anomaly_signal(self._session, context.tenant, RETAIL_MODULE_CODE, self._prediction_service)
        return ToolResult(
            success=True,
            data={
                "anomalies_count": signal.value,
                "total_records_scanned": signal.metadata.get("total_records_scanned"),
            },
            metadata={"model_capability": "anomaly_detection", "task_code": "anomaly"},
        )


class PredictionSummaryArgs(ToolArguments):
    pass


class GetPredictionSummaryTool(PredictiveAITool):
    """Toujours disponible : liste, sans jargon ML, quelles prédictions le tenant peut utiliser.

    N'exécute AUCUNE inférence : lit uniquement le Model Registry (existence
    d'un modèle actif par tâche), jamais de calcul lourd, jamais d'appel au
    fournisseur LLM.
    """

    name = "get_prediction_summary"
    description = (
        "List which predictive insights (churn risk, customer segments, demand forecast, sales "
        "forecast, anomaly detection) are currently available for this tenant, without running "
        "any prediction."
    )
    input_schema = PredictionSummaryArgs
    required_permissions = ("ai:use",)
    task_type = "prediction_summary"
    evaluate_freshness_flag = False

    def __init__(self, session: Session) -> None:
        self._session = session

    async def build_prediction(self, context: ToolExecutionContext, arguments: PredictionSummaryArgs) -> ToolResult:
        available = {}
        for task_code, label in _PREDICTIVE_TASK_CODES:
            model_type = resolve_active_model_type(self._session, context.tenant, RETAIL_MODULE_CODE, task_code)
            available[label] = model_type is not None
        return ToolResult(success=True, data={"available_predictions": available})
