"""Analyse de portefeuille client (Phase 22, BLOC B) : combine churn +
segmentation, et recommendation, sur toutes les lignes du dernier dataset
importe, pour produire des signaux agreges (jamais une decision par client
isole).

Reutilise tel quel PredictionService/PredictionRuntime (aucun second moteur
de prediction) : ce service se contente d'appeler PredictionService.predict
une fois par client, exactement comme le ferait n'importe quel appelant de
/predict, puis agrege les resultats en BusinessSignal (jamais de terme
technique, jamais de donnee inventee).
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import Dataset, DatasetProfile
from backend.app.services.business_signal_bridge import (
    signal_from_business_trend,
    signal_from_recommendation,
    signal_from_segmentation,
    signal_from_sentiment,
)
from backend.app.services.prediction_runtime import resolve_active_model_type, resolve_executor
from backend.app.services.target_resolution_service import TargetColumnUnresolved, TargetResolutionService
from modules.retailsense.training_specs import MODULE_TRAINING_SPECS
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.decision_intelligence.contracts import BusinessSignal, SignalDirection
from shared.ai_engine.nlp.sentiment import aggregate_sentiment
from shared.ai_engine.prediction.service import PredictionService


class PortfolioAnalysisUnavailable(ValueError):
    """Aucune analyse de portefeuille possible (dataset ou modeles manquants)."""


def _latest_dataset(session: Session, tenant: TenantContext, module_code: str) -> Dataset | None:
    return session.scalar(
        select(Dataset)
        .join(DatasetProfile, DatasetProfile.dataset_id == Dataset.id)
        .where(Dataset.company_id == tenant.company_id, DatasetProfile.module_code == module_code)
        .order_by(Dataset.uploaded_at.desc())
    )


def build_churn_segmentation_signals(
    session: Session,
    tenant: TenantContext,
    module_code: str,
    prediction_service: PredictionService,
) -> tuple[BusinessSignal, BusinessSignal]:
    """Predit churn + segment pour chaque client du dernier dataset importe.

    Retourne deux signaux agreges : le nombre de clients a risque de depart,
    et parmi eux, combien appartiennent au segment le plus frequent (proxy
    honnete de "forte valeur" en l'absence d'une colonne monetaire dediee) -
    jamais une donnee inventee, uniquement calculee depuis des predictions
    reelles sur des donnees reellement importees.
    """

    churn_type = resolve_active_model_type(session, tenant, module_code, "churn")
    segmentation_type = resolve_active_model_type(session, tenant, module_code, "segmentation")
    if churn_type is None or segmentation_type is None:
        raise PortfolioAnalysisUnavailable("No active churn or segmentation model for this company.")

    dataset = _latest_dataset(session, tenant, module_code)
    if dataset is None:
        raise PortfolioAnalysisUnavailable("No dataset available to analyze this company's customers.")

    data = pd.read_csv(dataset.source)
    resolver = TargetResolutionService()
    churn_spec = MODULE_TRAINING_SPECS[module_code]["churn"]
    try:
        churn_target = resolver.resolve(list(data.columns), churn_spec.target_aliases)
    except TargetColumnUnresolved:
        raise PortfolioAnalysisUnavailable("Churn target column could not be resolved for this dataset.")

    churn_executor = resolve_executor(churn_type)
    segmentation_executor = resolve_executor(segmentation_type)

    at_risk_customers: list[str] = []
    segment_by_customer: dict[str, object] = {}
    for row_index, row in data.iterrows():
        customer_id = str(row.get("customer_id", row_index))
        churn_features = row.drop(labels=[churn_target]).to_dict()
        churn_outcome = prediction_service.predict(tenant, module_code, "churn", churn_features, churn_executor)
        if churn_outcome.get("result") not in (1, 1.0, True, "1"):
            continue
        at_risk_customers.append(customer_id)
        segmentation_outcome = prediction_service.predict(
            tenant, module_code, "segmentation", row.to_dict(), segmentation_executor
        )
        segment_by_customer[customer_id] = segmentation_outcome.get("result")

    if not at_risk_customers:
        raise PortfolioAnalysisUnavailable("No customers currently at churn risk.")

    segment_counts: dict[object, int] = {}
    for segment in segment_by_customer.values():
        segment_counts[segment] = segment_counts.get(segment, 0) + 1
    high_value_segment = max(segment_counts, key=segment_counts.get)
    high_value_at_risk = [
        customer_id for customer_id, segment in segment_by_customer.items() if segment == high_value_segment
    ]

    churn_signal = BusinessSignal(
        company_id=tenant.company_id,
        module_code=module_code,
        task_code="churn",
        capability="classification",
        entity=f"{len(at_risk_customers)} clients a risque de depart",
        metric="at_risk_customers_count",
        value=float(len(at_risk_customers)),
        direction=SignalDirection.RISK,
        confidence=0.7,
        metadata={"at_risk_customer_ids": tuple(at_risk_customers)},
    )
    segmentation_signal = BusinessSignal(
        company_id=tenant.company_id,
        module_code=module_code,
        task_code="segmentation",
        capability="segmentation",
        entity=f"segment {high_value_segment}",
        metric="high_value_at_risk_count",
        value=float(len(high_value_at_risk)),
        direction=SignalDirection.STABLE,
        confidence=0.6,
        metadata={
            "high_value_at_risk_customer_ids": tuple(high_value_at_risk),
            "high_value_segment": str(high_value_segment),
        },
    )
    return churn_signal, segmentation_signal


def build_recommendation_opportunity_signal(
    session: Session,
    tenant: TenantContext,
    module_code: str,
    prediction_service: PredictionService,
) -> BusinessSignal:
    """Compte, parmi les clients du dernier dataset importe, combien recoivent
    au moins une recommandation (opportunite de vente croisee)."""

    recommendation_type = resolve_active_model_type(session, tenant, module_code, "recommendation")
    if recommendation_type is None:
        raise PortfolioAnalysisUnavailable("No active recommender for this company.")

    dataset = _latest_dataset(session, tenant, module_code)
    if dataset is None:
        raise PortfolioAnalysisUnavailable("No dataset available to analyze this company's customers.")

    data = pd.read_csv(dataset.source)
    resolver = TargetResolutionService()
    spec = MODULE_TRAINING_SPECS[module_code]["recommendation"]
    try:
        user_column = resolver.resolve(list(data.columns), spec.user_column_aliases)
    except TargetColumnUnresolved:
        raise PortfolioAnalysisUnavailable("Customer column could not be resolved for this dataset.")

    executor = resolve_executor(recommendation_type)
    customers = sorted({str(value) for value in data[user_column].dropna()})

    opportunity_customers: list[str] = []
    for customer_id in customers:
        outcome = prediction_service.predict(
            tenant, module_code, "recommendation", {"customer_id": customer_id, "top_k": spec.top_k}, executor
        )
        if outcome.get("result"):
            opportunity_customers.append(customer_id)

    if not opportunity_customers:
        raise PortfolioAnalysisUnavailable("No cross-sell opportunity detected for this company's customers.")

    return signal_from_recommendation(
        tenant.company_id,
        module_code,
        "recommendation",
        f"{len(opportunity_customers)} clients",
        recommended_items=opportunity_customers,
        confidence=0.6,
    )


# Alias de colonne temporelle (Phase 24) : optionnelle, reutilisee pour
# ordonner chronologiquement les predictions de tendance (demande/prix) —
# meme liste que "weekly_forecast" (training_specs.py), jamais une colonne
# inventee pour une entreprise precise.
_TREND_TIMESTAMP_ALIASES: tuple[str, ...] = ("date", "order_date", "created_at", "timestamp", "datetime")
# Nombre minimal de lignes pour scinder les predictions en "recent"/"historique"
# (meme seuil que la tendance de sentiment, Phase 23).
_MINIMUM_TREND_ROWS = 4


def _predict_regression_trend(
    session: Session,
    tenant: TenantContext,
    module_code: str,
    task_code: str,
    prediction_service: PredictionService,
) -> tuple[float, float | None, int]:
    """Predit une mesure de regression (demande/prix) sur chaque ligne du

    dernier dataset importe, puis compare la moyenne predite recente a la
    moyenne reelle historique (meme principe de tendance temporelle que
    `aggregate_sentiment`, Phase 23) — jamais une metrique fabriquee : si
    aucune colonne temporelle n'est resolue, la moyenne globale predite est
    comparee a la moyenne globale reelle (repli honnete, souvent STABLE).
    """

    model_type = resolve_active_model_type(session, tenant, module_code, task_code)
    if model_type is None:
        raise PortfolioAnalysisUnavailable(f"No active model for task '{task_code}' for this company.")

    dataset = _latest_dataset(session, tenant, module_code)
    if dataset is None:
        raise PortfolioAnalysisUnavailable("No dataset available to analyze this company's customers.")

    data = pd.read_csv(dataset.source)
    resolver = TargetResolutionService()
    spec = MODULE_TRAINING_SPECS[module_code][task_code]
    try:
        target_column = resolver.resolve(list(data.columns), spec.target_aliases)
    except TargetColumnUnresolved:
        raise PortfolioAnalysisUnavailable(f"Target column could not be resolved for task '{task_code}'.")

    timestamp_column = _resolve_optional_column(list(data.columns), _TREND_TIMESTAMP_ALIASES)
    use_trend_split = timestamp_column is not None and len(data) >= _MINIMUM_TREND_ROWS
    ordered = data.sort_values(timestamp_column) if use_trend_split else data

    executor = resolve_executor(model_type)
    predicted_values: list[float] = []
    for _, row in ordered.iterrows():
        features = row.drop(labels=[target_column]).to_dict()
        outcome = prediction_service.predict(tenant, module_code, task_code, features, executor)
        predicted_values.append(float(outcome.get("result", 0.0)))

    if not predicted_values:
        raise PortfolioAnalysisUnavailable(f"No rows available to predict '{task_code}'.")

    if use_trend_split:
        midpoint = len(ordered) // 2
        recent_predicted = predicted_values[midpoint:]
        historical_actual = ordered[target_column].tolist()[:midpoint]
        value = sum(recent_predicted) / len(recent_predicted)
        previous_value = sum(historical_actual) / len(historical_actual) if historical_actual else None
    else:
        value = sum(predicted_values) / len(predicted_values)
        previous_value = float(ordered[target_column].mean())

    return value, previous_value, len(ordered)


def build_demand_signal(
    session: Session,
    tenant: TenantContext,
    module_code: str,
    prediction_service: PredictionService,
) -> BusinessSignal:
    """Tendance de demande sur le dernier dataset importe (Phase 24).

    Jamais une decision par produit isole : une seule mesure agregee, avec
    une direction OPPORTUNITY/RISK/STABLE fondee sur la variation reelle
    (voir `signal_from_business_trend`).
    """

    value, previous_value, row_count = _predict_regression_trend(
        session, tenant, module_code, "demand", prediction_service
    )
    return signal_from_business_trend(
        tenant.company_id,
        module_code,
        "demand",
        entity=f"{row_count} produits",
        metric="demand",
        value=value,
        previous_value=previous_value,
        confidence=0.6,
    )


def build_price_signal(
    session: Session,
    tenant: TenantContext,
    module_code: str,
    prediction_service: PredictionService,
) -> BusinessSignal:
    """Tendance de prix sur le dernier dataset importe (Phase 24).

    Meme principe que `build_demand_signal` : jamais une decision par produit
    isole, une seule mesure agregee de tendance de prix.
    """

    value, previous_value, row_count = _predict_regression_trend(
        session, tenant, module_code, "price", prediction_service
    )
    return signal_from_business_trend(
        tenant.company_id,
        module_code,
        "price",
        entity=f"{row_count} produits",
        metric="price",
        value=value,
        previous_value=previous_value,
        confidence=0.6,
    )


def build_segmentation_signal(
    session: Session,
    tenant: TenantContext,
    module_code: str,
    prediction_service: PredictionService,
) -> BusinessSignal:
    """Segmente tous les clients du dernier dataset importe et identifie le

    segment dominant (part du portefeuille) — independamment de tout risque
    de depart (contrairement au signal de segmentation combine dans
    `build_churn_segmentation_signals`, qui repond a une autre question
    metier : "quels clients a forte valeur risquent de partir ?").
    """

    segmentation_type = resolve_active_model_type(session, tenant, module_code, "segmentation")
    if segmentation_type is None:
        raise PortfolioAnalysisUnavailable("No active segmentation model for this company.")

    dataset = _latest_dataset(session, tenant, module_code)
    if dataset is None:
        raise PortfolioAnalysisUnavailable("No dataset available to analyze this company's customers.")

    data = pd.read_csv(dataset.source)
    executor = resolve_executor(segmentation_type)

    segment_counts: dict[object, int] = {}
    total = 0
    for _, row in data.iterrows():
        outcome = prediction_service.predict(tenant, module_code, "segmentation", row.to_dict(), executor)
        segment = outcome.get("result")
        segment_counts[segment] = segment_counts.get(segment, 0) + 1
        total += 1

    if total == 0:
        raise PortfolioAnalysisUnavailable("No customers available to segment for this company.")

    dominant_segment, dominant_count = max(segment_counts.items(), key=lambda item: item[1])
    return signal_from_segmentation(
        tenant.company_id,
        module_code,
        "segmentation",
        f"segment {dominant_segment}",
        dominant_count / total,
    )


# Nombre maximal d'identifiants de prédiction (client/enregistrement) exposés
# dans les métadonnées d'un signal — jamais des milliers de lignes envoyées
# au LLM (voir `ToolExecutor.MAX_TOOL_RESULT_CHARS`, même principe de
# troncature défensive appliqué en amont, côté métier).
_MAX_EXPOSED_RECORD_IDS = 20


def build_sales_forecast_signal(
    session: Session,
    tenant: TenantContext,
    module_code: str,
    prediction_service: PredictionService,
    horizon: int | None = None,
) -> BusinessSignal:
    """Prévision de ventes (Phase 31) via le modèle "weekly_forecast" déjà entraîné.

    Réutilise tel quel `PredictionService`/`ForecastingPredictionExecutor` :
    aucun second moteur de prévision, aucun réentraînement. L'horizon
    demandé ne dépasse jamais celui convenu à l'entraînement (voir
    `ForecastingTrainingSpec.horizon`) sauf si explicitement fourni par
    l'appelant (ex. l'utilisateur demande un horizon plus court).
    """

    model_type = resolve_active_model_type(session, tenant, module_code, "weekly_forecast")
    if model_type is None:
        raise PortfolioAnalysisUnavailable("No active sales forecast model for this company.")

    spec = MODULE_TRAINING_SPECS[module_code]["weekly_forecast"]
    effective_horizon = horizon if horizon and horizon > 0 else spec.horizon
    executor = resolve_executor(model_type)
    outcome = prediction_service.predict(
        tenant, module_code, "weekly_forecast", {"horizon": effective_horizon}, executor
    )
    result = outcome.get("result") or {}
    forecast_points = list(result.get("forecast") or [])
    if not forecast_points:
        raise PortfolioAnalysisUnavailable("No sales forecast could be produced for this company.")

    forecast_values = [float(point) for point in forecast_points]
    return BusinessSignal(
        company_id=tenant.company_id,
        module_code=module_code,
        task_code="weekly_forecast",
        capability="forecasting",
        entity=f"next {len(forecast_values)} periods",
        metric="forecasted_total",
        value=sum(forecast_values),
        direction=SignalDirection.STABLE,
        confidence=0.6,
        metadata={
            "forecast_points": tuple(forecast_values),
            "horizon": effective_horizon,
        },
    )


def build_anomaly_signal(
    session: Session,
    tenant: TenantContext,
    module_code: str,
    prediction_service: PredictionService,
) -> BusinessSignal:
    """Détecte les enregistrements anormaux (Phase 31) via le modèle "anomaly" actif.

    Même principe que `build_churn_segmentation_signals` : jamais une décision
    par enregistrement isolé, un seul signal agrégé (nombre d'anomalies), avec
    au plus `_MAX_EXPOSED_RECORD_IDS` identifiants exposés en métadonnée.
    """

    model_type = resolve_active_model_type(session, tenant, module_code, "anomaly")
    if model_type is None:
        raise PortfolioAnalysisUnavailable("No active anomaly detection model for this company.")

    dataset = _latest_dataset(session, tenant, module_code)
    if dataset is None:
        raise PortfolioAnalysisUnavailable("No dataset available to analyze this company's data.")

    data = pd.read_csv(dataset.source)
    executor = resolve_executor(model_type)

    anomalous_ids: list[str] = []
    total = 0
    for row_index, row in data.iterrows():
        outcome = prediction_service.predict(tenant, module_code, "anomaly", row.to_dict(), executor)
        total += 1
        if outcome.get("result") in (-1, -1.0, "-1"):
            identifier = row.get("order_id", row.get("customer_id", row_index))
            anomalous_ids.append(str(identifier))

    if not anomalous_ids:
        raise PortfolioAnalysisUnavailable("No anomalies detected in this company's data.")

    return BusinessSignal(
        company_id=tenant.company_id,
        module_code=module_code,
        task_code="anomaly",
        capability="anomaly_detection",
        entity=f"{len(anomalous_ids)} records",
        metric="anomalies_count",
        value=float(len(anomalous_ids)),
        direction=SignalDirection.RISK,
        confidence=0.6,
        metadata={
            "anomalous_record_ids": tuple(anomalous_ids[:_MAX_EXPOSED_RECORD_IDS]),
            "total_records_scanned": total,
        },
    )


# Alias de colonnes texte (Phase 23) : jamais une colonne inventée, uniquement
# les noms réels observés chez différentes entreprises. Résolue par alias
# exact/sous-chaîne (même principe que `_has_sentiment_signal`), PAS par la
# similarité sémantique générique de `TargetResolutionService` : son seuil
# (0.72) confond à tort des colonnes d'identifiants comme "customer_id" avec
# l'alias "customer_review" (ratio ~0.77) — une validation de contenu
# (texte libre réel, pas un identifiant court) protège contre ce faux positif.
_SENTIMENT_TEXT_ALIASES: tuple[str, ...] = (
    "review_text",
    "comment",
    "feedback",
    "message",
    "customer_review",
    "survey_response",
    "ticket_message",
)
_SENTIMENT_TEXT_NAME_TOKENS: tuple[str, ...] = ("text", "comment", "review", "feedback", "message")
# Colonnes optionnelles : si absentes, l'analyse reste possible mais sans
# thème le plus négatif / sans tendance temporelle (dégradation gracieuse,
# jamais une erreur).
_SENTIMENT_ENTITY_ALIASES: tuple[str, ...] = ("product_id", "product", "sku", "service", "product_code")
_SENTIMENT_TIMESTAMP_ALIASES: tuple[str, ...] = ("date", "order_date", "created_at", "timestamp", "review_date")
# Nombre moyen de mots minimum, sur un échantillon, pour qu'une colonne soit
# considérée comme du texte libre exploitable (écarte les identifiants/codes
# courts même si leur nom ressemble à un alias attendu).
_MINIMUM_AVERAGE_WORD_COUNT = 3.0


def _looks_like_free_text(series: pd.Series) -> bool:
    sample = series.dropna().astype(str).head(20)
    if sample.empty:
        return False
    average_word_count = sum(len(value.split()) for value in sample) / len(sample)
    return average_word_count >= _MINIMUM_AVERAGE_WORD_COUNT


def _resolve_text_column(data: pd.DataFrame) -> str | None:
    """Trouve la colonne de texte exploitable, jamais une colonne inventée.

    Alias exact d'abord, puis sous-chaîne dans le nom de colonne (même
    principe que `TaskResolutionService._has_sentiment_signal`) — toujours
    confirmé par le contenu réel (texte libre, pas un identifiant court).
    """

    lower_to_actual = {str(column).lower(): column for column in data.columns}
    for alias in _SENTIMENT_TEXT_ALIASES:
        actual = lower_to_actual.get(alias)
        if actual is not None and _looks_like_free_text(data[actual]):
            return actual

    for column in data.columns:
        lowered = str(column).lower()
        if any(token in lowered for token in _SENTIMENT_TEXT_NAME_TOKENS) and _looks_like_free_text(data[column]):
            return column

    return None



def _resolve_optional_column(columns: list[str], aliases: tuple[str, ...]) -> str | None:
    """Comme `TargetResolutionService.resolve`, mais renvoie `None` au lieu de
    lever une exception : utilisé pour les colonnes optionnelles du sentiment."""

    try:
        return TargetResolutionService().resolve(columns, aliases)
    except TargetColumnUnresolved:
        return None


def build_sentiment_signal(
    session: Session,
    tenant: TenantContext,
    module_code: str,
) -> BusinessSignal:
    """Analyse le sentiment sur le dernier dataset importé (Phase 23, Tier 1).

    Contrairement à churn/segmentation/recommendation, aucun modèle actif
    n'est nécessaire : le Tier 1 est un modèle de base par lexique, sans
    entraînement propre à l'entreprise (voir `shared/ai_engine/nlp/sentiment.py`).
    Lève `PortfolioAnalysisUnavailable` si aucun texte exploitable n'existe
    pour ce dataset (jamais une colonne inventée).
    """

    dataset = _latest_dataset(session, tenant, module_code)
    if dataset is None:
        raise PortfolioAnalysisUnavailable("No dataset available to analyze this company's customers.")

    data = pd.read_csv(dataset.source)
    columns = list(data.columns)
    text_column = _resolve_text_column(data)
    if text_column is None:
        raise PortfolioAnalysisUnavailable("No exploitable text column found for sentiment analysis.")

    entity_column = _resolve_optional_column(columns, _SENTIMENT_ENTITY_ALIASES)
    timestamp_column = _resolve_optional_column(columns, _SENTIMENT_TIMESTAMP_ALIASES)

    rows = data.to_dict("records")
    aggregate = aggregate_sentiment(rows, text_column, entity_column, timestamp_column)
    if aggregate.total_analyzed == 0:
        raise PortfolioAnalysisUnavailable("No exploitable text found for sentiment analysis.")

    return signal_from_sentiment(
        tenant.company_id,
        module_code,
        "sentiment",
        f"{aggregate.total_analyzed} avis clients",
        aggregate,
    )


def gather_portfolio_signals(
    session: Session,
    tenant: TenantContext,
    module_code: str,
    prediction_service: PredictionService,
) -> list[BusinessSignal]:
    """Rassemble tous les signaux de portefeuille disponibles pour ce tenant.

    Réutilisé par `/portfolio-decisions` (Phase 22/24) et `/portfolio-opportunities`
    (Phase 25) — un seul point de collecte, jamais dupliqué : chaque capacité
    manquante (modèle non entraîné, dataset absent) est ignorée proprement,
    jamais une erreur bloquante pour les autres capacités disponibles.
    """

    signals: list[BusinessSignal] = []

    try:
        churn_signal, segmentation_signal = build_churn_segmentation_signals(
            session, tenant, module_code, prediction_service
        )
        signals.extend([churn_signal, segmentation_signal])
    except PortfolioAnalysisUnavailable:
        pass

    try:
        signals.append(build_recommendation_opportunity_signal(session, tenant, module_code, prediction_service))
    except PortfolioAnalysisUnavailable:
        pass

    try:
        signals.append(build_sentiment_signal(session, tenant, module_code))
    except PortfolioAnalysisUnavailable:
        pass

    try:
        signals.append(build_demand_signal(session, tenant, module_code, prediction_service))
    except PortfolioAnalysisUnavailable:
        pass

    try:
        signals.append(build_price_signal(session, tenant, module_code, prediction_service))
    except PortfolioAnalysisUnavailable:
        pass

    try:
        signals.append(build_segmentation_signal(session, tenant, module_code, prediction_service))
    except PortfolioAnalysisUnavailable:
        pass

    return signals
