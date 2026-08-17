"""Spécifications d'entraînement automatique propres au module RetailSense.

Cette configuration vit dans la couche métier (`modules/`), jamais dans
`shared/ai_engine` : elle décrit UNIQUEMENT la tâche métier — alias de
colonnes pour la cible, famille, type d'entraînement et modèles autorisés.
Tous les estimateurs et grilles d'hyperparamètres proviennent exclusivement
de `shared/ai_engine/hyperparameters/` (source unique de vérité).

Pour câbler une nouvelle tâche automatique dans une famille déjà supportée
(classification/regression/clustering/anomaly_detection), il suffit d'ajouter
une entrée à `MODULE_TRAINING_SPECS` — ni `shared/ai_engine`, ni le
`TrainingDispatcher`, n'ont besoin d'être modifiés. Ajouter une NOUVELLE
famille (ex. forecasting temporel, NLP) reste une opération ponctuelle dans
`shared/ai_engine/hyperparameters/` + `shared/ai_engine/training/` +
`TrainingService`/`TrainingDispatcher` (voir Phase 19 : famille
"anomaly_detection" ajoutée ainsi) — jamais un second moteur parallèle.

Voir `CapabilityStatus`/`MODULE_TASK_STATUS`/`get_capability_status()`
ci-dessous pour la séparation explicite entre tâches détectables
(`TaskResolutionService`) et tâches réellement câblées ici.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from sklearn.base import BaseEstimator

from shared.ai_engine.hyperparameters import anomaly as anomaly_hyperparameters
from shared.ai_engine.hyperparameters import classification as classification_hyperparameters
from shared.ai_engine.hyperparameters import clustering as clustering_hyperparameters
from shared.ai_engine.hyperparameters import forecasting as forecasting_hyperparameters
from shared.ai_engine.hyperparameters import recommendation as recommendation_hyperparameters
from shared.ai_engine.hyperparameters import regression as regression_hyperparameters


def _filter_models(values: dict[str, Any], allowed_models: tuple[str, ...] | None) -> dict[str, Any]:
    """Restreint un dictionnaire modèle->valeur à `allowed_models` (None = tous)."""

    if allowed_models is None:
        return values
    return {name: value for name, value in values.items() if name in allowed_models}


@dataclass(frozen=True, slots=True)
class ClassificationTrainingSpec:
    """Décrit comment entraîner automatiquement une tâche de classification binaire."""

    task_code: str
    # Capacité générique (voir `shared.ai_engine.task_resolution.service`) que
    # cette tâche satisfait — seule source utilisée par le dispatcher pour
    # décider si les DONNÉES importées permettent réellement cette tâche.
    capability: str
    target_aliases: tuple[str, ...]
    family: str = "classification"
    training_type: str = "supervised"
    # None = tous les modèles disponibles dans shared/ai_engine/hyperparameters.
    allowed_models: tuple[str, ...] | None = None

    def build_estimators(self) -> dict[str, BaseEstimator]:
        """Modèles autorisés pour cette tâche, filtrés depuis la source unique de vérité."""

        return _filter_models(classification_hyperparameters.build_estimators(), self.allowed_models)

    def build_parameter_spaces(self) -> dict[str, Mapping[str, Any]]:
        """Grilles d'hyperparamètres des modèles autorisés pour cette tâche."""

        return _filter_models(classification_hyperparameters.build_parameter_spaces(), self.allowed_models)


@dataclass(frozen=True, slots=True)
class RegressionTrainingSpec:
    """Décrit comment entraîner automatiquement une tâche de régression.

    Même architecture que `ClassificationTrainingSpec` : seule source de
    vérité pour les estimateurs/grilles = `shared.ai_engine.hyperparameters.regression`.
    """

    task_code: str
    # Capacité générique que cette tâche satisfait (ex. "regression") —
    # comparée aux capacités détectées par `TaskResolutionService` sur les
    # données réellement importées, jamais décidée seule par ce fichier.
    capability: str
    target_aliases: tuple[str, ...]
    family: str = "regression"
    training_type: str = "supervised"
    # None = tous les modèles disponibles dans shared/ai_engine/hyperparameters.
    allowed_models: tuple[str, ...] | None = None

    def build_estimators(self) -> dict[str, BaseEstimator]:
        """Modèles autorisés pour cette tâche, filtrés depuis la source unique de vérité."""

        return _filter_models(regression_hyperparameters.build_estimators(), self.allowed_models)

    def build_parameter_spaces(self) -> dict[str, Mapping[str, Any]]:
        """Grilles d'hyperparamètres des modèles autorisés pour cette tâche."""

        return _filter_models(regression_hyperparameters.build_parameter_spaces(), self.allowed_models)


@dataclass(frozen=True, slots=True)
class ClusteringTrainingSpec:
    """Décrit comment entraîner automatiquement une tâche de regroupement.

    Même architecture que `ClassificationTrainingSpec`/`RegressionTrainingSpec` :
    seule source de vérité pour les estimateurs/grilles =
    `shared.ai_engine.hyperparameters.clustering`. Non supervisé : pas de
    `target_aliases`, aucune colonne cible n'est résolue pour cette famille.
    """

    task_code: str
    # Capacité générique que cette tâche satisfait (ex. "segmentation").
    capability: str
    family: str = "clustering"
    training_type: str = "unsupervised"
    # None = tous les modèles disponibles dans shared/ai_engine/hyperparameters.
    allowed_models: tuple[str, ...] | None = None

    def build_estimators(self) -> dict[str, BaseEstimator]:
        """Modèles autorisés pour cette tâche, filtrés depuis la source unique de vérité."""

        return _filter_models(clustering_hyperparameters.build_estimators(), self.allowed_models)

    def build_parameter_spaces(self) -> dict[str, Mapping[str, Any]]:
        """Grilles d'hyperparamètres des modèles autorisés pour cette tâche."""

        return _filter_models(clustering_hyperparameters.build_parameter_spaces(), self.allowed_models)


@dataclass(frozen=True, slots=True)
class AnomalyTrainingSpec:
    """Décrit comment entraîner automatiquement une tâche de détection d'anomalies.

    Même architecture que `ClusteringTrainingSpec` : seule source de vérité pour
    les estimateurs/grilles = `shared.ai_engine.hyperparameters.anomaly`. Non
    supervisé : pas de `target_aliases`, aucune colonne cible n'est résolue
    pour cette famille (comme le clustering).
    """

    task_code: str
    # Capacité générique que cette tâche satisfait ("anomaly_detection").
    capability: str
    family: str = "anomaly_detection"
    training_type: str = "unsupervised"
    # None = tous les modèles disponibles dans shared/ai_engine/hyperparameters
    # (aujourd'hui : uniquement IsolationForest).
    allowed_models: tuple[str, ...] | None = None

    def build_estimators(self) -> dict[str, BaseEstimator]:
        """Modèles autorisés pour cette tâche, filtrés depuis la source unique de vérité."""

        return _filter_models(anomaly_hyperparameters.build_estimators(), self.allowed_models)

    def build_parameter_spaces(self) -> dict[str, Mapping[str, Any]]:
        """Grilles d'hyperparamètres des modèles autorisés pour cette tâche."""

        return _filter_models(anomaly_hyperparameters.build_parameter_spaces(), self.allowed_models)


@dataclass(frozen=True, slots=True)
class ForecastingTrainingSpec:
    """Décrit comment entraîner automatiquement une tâche de prévision temporelle.

    Comme les autres specs : aucune colonne cible/temporelle n'est câblée en
    dur pour une entreprise/un CSV précis — seuls des alias génériques sont
    déclarés, résolus par `TargetResolutionService` (cible ET colonne
    temporelle, ce même service étant assez générique pour les deux, voir
    `TrainingDispatcher._build_and_train`). Les familles statistiques (naïf,
    naïf saisonnier, ARIMA, SARIMA) ne sont PAS des estimateurs sklearn : seul
    ``gradient_boosting_lags`` provient de `shared.ai_engine.hyperparameters`
    (source unique de vérité pour ce candidat).
    """

    task_code: str
    capability: str
    target_aliases: tuple[str, ...]
    time_column_aliases: tuple[str, ...]
    horizon: int = 1
    minimum_observations: int = 12
    seasonal_period: int = 7
    frequency: str = "auto"
    aggregation: str = "sum"
    family: str = "forecasting"
    training_type: str = "temporal_supervised"
    # None = toutes les familles de `ALL_FORECASTING_FAMILIES` (statistiques
    # + gradient_boosting_lags).
    allowed_models: tuple[str, ...] | None = None

    @property
    def candidate_families(self) -> tuple[str, ...]:
        if self.allowed_models is None:
            return forecasting_hyperparameters.ALL_FORECASTING_FAMILIES
        return tuple(
            family
            for family in forecasting_hyperparameters.ALL_FORECASTING_FAMILIES
            if family in self.allowed_models
        )

    def build_estimators(self) -> dict[str, BaseEstimator]:
        """Seul estimateur sklearn de cette famille (`gradient_boosting_lags`), filtré."""

        return _filter_models(forecasting_hyperparameters.build_estimators(), self.allowed_models)

    def build_parameter_spaces(self) -> dict[str, Mapping[str, Any]]:
        """Grille d'hyperparamètres de `gradient_boosting_lags`, filtrée."""

        return _filter_models(forecasting_hyperparameters.build_parameter_spaces(), self.allowed_models)


@dataclass(frozen=True, slots=True)
class RecommendationTrainingSpec:
    """Décrit comment entraîner automatiquement un Recommendation Engine (Phase 22).

    Contrairement aux familles supervisées, il n'existe pas UNE colonne cible :
    trois "concepts" génériques sont résolus séparément par le même
    `TargetResolutionService` que les autres tâches (alias exacts puis
    similarité sémantique) — client, produit (tous deux obligatoires), et
    signal d'interaction (optionnel : à défaut, les interactions restent
    implicites, comptées comme une simple présence). Jamais de colonne
    inventée : si client ou produit ne peuvent pas être résolus, la tâche
    échoue proprement (voir `TrainingDispatcher._build_and_train`).
    """

    task_code: str
    # Capacité générique que cette tâche satisfait ("recommendation").
    capability: str
    user_column_aliases: tuple[str, ...]
    item_column_aliases: tuple[str, ...]
    interaction_column_aliases: tuple[str, ...]
    family: str = "recommendation"
    training_type: str = "collaborative_filtering"
    # Nombre minimum d'interactions client/produit exploitables pour accepter
    # d'entraîner un recommender (voir `train_recommender.InsufficientInteractionsError`).
    minimum_interactions: int = 20
    top_k: int = 5
    # None = toutes les configurations de `shared/ai_engine/hyperparameters/recommendation.py`.
    allowed_models: tuple[str, ...] | None = None

    def build_estimators(self) -> dict[str, Any]:
        """Aucun estimateur sklearn pour cette famille (voir hyperparameters/recommendation.py)."""

        return _filter_models(recommendation_hyperparameters.build_estimators(), self.allowed_models)

    def build_parameter_spaces(self) -> dict[str, Mapping[str, Any]]:
        """Grille explicite (n_neighbors/weighting) comparée par validation offline."""

        return _filter_models(recommendation_hyperparameters.build_parameter_spaces(), self.allowed_models)


# Phase 18.2 : plusieurs tâches automatiques peuvent désormais être câblées
# par module (dict module_code -> {task_code: spec}). Le dispatcher n'exécute
# une tâche que si `TaskResolutionService` détecte, à partir des données
# réellement importées, que sa `capability` est possible ET autorisée par le
# module (voir `modules/catalog.py` + `modules/base.py`). Étendre en ajoutant
# une entrée par tâche ci-dessous — ni `shared/ai_engine`, ni le
# `TrainingDispatcher`, n'ont besoin d'être modifiés.
MODULE_TRAINING_SPECS: dict[
    str,
    dict[
        str,
        ClassificationTrainingSpec
        | RegressionTrainingSpec
        | ClusteringTrainingSpec
        | AnomalyTrainingSpec
        | ForecastingTrainingSpec
        | RecommendationTrainingSpec,
    ],
] = {
    "retail": {
        "bad_review": ClassificationTrainingSpec(
            task_code="bad_review",
            capability="classification",
            target_aliases=(
                "bad_review",
                "is_bad_review",
                "negative_review",
                "review_negative",
                "bad",
            ),
        ),
        "price": RegressionTrainingSpec(
            task_code="price",
            capability="regression",
            target_aliases=(
                "price",
                "unit_price",
                "selling_price",
                "sale_price",
            ),
        ),
        # Phase 19 : même famille/moteur que "price" (RegressionTrainingSpec,
        # capability="regression") — seuls les alias de cible changent. Les
        # deux tâches peuvent se déclencher indépendamment sur le même
        # dataset (voir TrainingDispatcher.dispatch) : chacune obtient son
        # propre AIJob/TrainingJob et son propre modèle actif.
        "demand": RegressionTrainingSpec(
            task_code="demand",
            capability="regression",
            target_aliases=(
                "quantity",
                "demand",
                "units_sold",
                "sales_quantity",
            ),
        ),
        # Phase 19 : réutilise ClusteringTrainingSpec/TrainingService.train_clustering
        # tel quel — aucun nouveau moteur clustering. `capability="segmentation"`
        # correspond à la capacité détectée par `TaskResolutionService`
        # (voir `_has_segmentation_signal`/`_normalize_module_task`).
        "segmentation": ClusteringTrainingSpec(
            task_code="segmentation",
            capability="segmentation",
        ),
        # Phase 19 : nouvelle famille "anomaly_detection", intégrée dans le
        # runtime ACTIF (TrainingService.train_anomaly_detection), suivant
        # exactement les conventions de classification/regression/clustering.
        # N'utilise PAS shared/ai_engine/families/anomaly/ (moteur orphelin,
        # non branché, voir audit Phase 19).
        "anomaly": AnomalyTrainingSpec(
            task_code="anomaly",
            capability="anomaly_detection",
        ),
        # Phase 21 : même famille/moteur que "bad_review" (ClassificationTrainingSpec,
        # capability="classification") — seuls les alias de cible changent. Couvre
        # la capacité métier "Churn / risque de perte client".
        "churn": ClassificationTrainingSpec(
            task_code="churn",
            capability="classification",
            target_aliases=(
                "churn",
                "is_churn",
                "churned",
            ),
        ),
        # Phase 20 : nouvelle famille "forecasting", intégrée dans le runtime
        # ACTIF (TrainingService.train_forecast) avec backtesting temporel réel
        # (jamais de train_test_split aléatoire, voir
        # `shared/ai_engine/training/train_forecaster.py`). N'utilise PAS
        # shared/ai_engine/families/forecasting/ (moteur orphelin, non câblé).
        "weekly_forecast": ForecastingTrainingSpec(
            task_code="weekly_forecast",
            capability="forecasting",
            target_aliases=(
                "quantity",
                "demand",
                "units_sold",
                "sales_quantity",
                "sales",
                "revenue",
                "orders",
                "total",
            ),
            time_column_aliases=(
                "date",
                "order_date",
                "created_at",
                "timestamp",
                "datetime",
                "period",
                "week",
            ),
            horizon=2,
            minimum_observations=12,
            seasonal_period=7,
        ),
        # Phase 22 : nouvelle famille "recommendation" (filtrage collaboratif
        # item-based, similarité cosine), intégrée dans le runtime ACTIF
        # (TrainingService.train_recommendation). Client/produit résolus via
        # le même TargetResolutionService que les autres tâches ; signal
        # d'interaction optionnel (à défaut : présence implicite).
        "recommendation": RecommendationTrainingSpec(
            task_code="recommendation",
            capability="recommendation",
            user_column_aliases=(
                "customer_id",
                "user_id",
                "client_id",
                "client_number",
                "buyer_id",
            ),
            item_column_aliases=(
                "product_id",
                "item_id",
                "sku",
                "product_code",
                "article_id",
            ),
            interaction_column_aliases=(
                "quantity",
                "units",
                "rating",
                "score",
                "purchase",
                "interaction",
            ),
        ),
    },
}


class CapabilityStatus(str, Enum):
    """Statut explicite d'une tâche métier vis-à-vis du runtime d'entraînement actif.

    - EXECUTABLE : câblée dans `MODULE_TRAINING_SPECS` — un `AIJob` réel peut
      être créé dès que `TaskResolutionService` détecte la capacité correspondante.
    - DETECTED_NOT_EXECUTABLE : `TaskResolutionService` peut détecter cette
      capacité sur les données importées, mais aucune configuration d'entraînement
      n'existe encore dans le runtime actif — le `TrainingDispatcher` ne doit
      jamais créer de job pour elle (voir `dispatch()` : seules les tâches
      présentes dans `MODULE_TRAINING_SPECS` peuvent produire un `AIJob`).
    - FUTURE_CAPABILITY : aucune détection, aucun entraînement — documentée
      pour une phase future, jamais un mécanisme actif aujourd'hui.
    """

    EXECUTABLE = "executable"
    DETECTED_NOT_EXECUTABLE = "detected_not_executable"
    FUTURE_CAPABILITY = "future_capability"


# Phase 19 : séparation explicite DETECTED / EXECUTABLE / DETECTED_NOT_EXECUTABLE
# / FUTURE_CAPABILITY, par tâche métier RetailSenseAI. Documente pourquoi une
# tâche déjà déclarée dans le catalogue (`modules/retailsense/tasks/`) et déjà
# détectable par `TaskResolutionService` n'a — ou a — une configuration
# d'entraînement réelle dans `MODULE_TRAINING_SPECS`.
MODULE_TASK_STATUS: dict[str, dict[str, CapabilityStatus]] = {
    "retail": {
        "bad_review": CapabilityStatus.EXECUTABLE,
        "price": CapabilityStatus.EXECUTABLE,
        "demand": CapabilityStatus.EXECUTABLE,
        "segmentation": CapabilityStatus.EXECUTABLE,
        "anomaly": CapabilityStatus.EXECUTABLE,
        # Phase 20 : forecasting temporel réel (backtesting, jamais de
        # train_test_split aléatoire) désormais câblé dans le runtime actif.
        "weekly_forecast": CapabilityStatus.EXECUTABLE,
        # Phase 21 : même moteur de classification que "bad_review", nouveaux
        # alias de cible uniquement.
        "churn": CapabilityStatus.EXECUTABLE,
        # Phase 22 : filtrage collaboratif item-based désormais câblé dans le
        # runtime ACTIF (même AI Engine générique, aucun moteur séparé).
        "recommendation": CapabilityStatus.EXECUTABLE,
        # Phase 23 : capacité rendue EXECUTABLE sans entrée dans
        # `MODULE_TRAINING_SPECS` — Tier 1 est un modèle de base par lexique
        # (voir `shared/ai_engine/nlp/sentiment.py`), sans entraînement propre
        # à chaque entreprise, donc aucun `AIJob`/Model Registry n'est
        # nécessaire pour ce premier niveau (voir `_STATELESS_EXECUTABLE_TASKS`
        # ci-dessous, exception documentée et testée par
        # `_check_status_consistency`). Le texte exploitable est résolu via le
        # même `TargetResolutionService` que les autres tâches (aucune
        # colonne inventée) — voir `portfolio_decision_service.build_sentiment_signal`.
        "sentiment": CapabilityStatus.EXECUTABLE,
        # Documentée comme capacité future : aucun entraînement ni génération
        # durant cette phase, jamais détectée par `TaskResolutionService`
        # (`_normalize_module_task` ne mappe "synthetic_data" à aucune des
        # capacités détectables).
        "synthetic_data": CapabilityStatus.FUTURE_CAPABILITY,
    },
}


def get_capability_status(module_code: str, task_code: str) -> CapabilityStatus:
    """Statut explicite d'une tâche (voir `CapabilityStatus`).

    Ne décide jamais seule si une tâche s'exécute réellement : `TrainingDispatcher`
    continue de baser sa décision uniquement sur la présence d'une entrée dans
    `MODULE_TRAINING_SPECS` (source unique de vérité) pour toutes les tâches
    SAUF celles listées dans `_STATELESS_EXECUTABLE_TASKS` (voir ce nom pour
    la justification). Cette fonction expose, de façon testable et explicite,
    l'intention déjà reflétée par cette présence/absence — jamais un
    mécanisme parallèle.
    """

    return MODULE_TASK_STATUS.get(module_code, {}).get(task_code, CapabilityStatus.DETECTED_NOT_EXECUTABLE)


# Phase 23 : tâches EXECUTABLE sans entrée dans `MODULE_TRAINING_SPECS`, par
# exception documentée — uniquement des capacités dont le Tier 1 est un
# modèle de base STATELESS (sans apprentissage propre à l'entreprise), donc
# sans `AIJob`/Model Registry nécessaire pour produire un premier résultat
# métier exploitable. "sentiment" est actuellement la seule (voir
# `shared/ai_engine/nlp/sentiment.py` et `portfolio_decision_service.py`).
# Toute future capacité stateless devra être ajoutée ici explicitement, avec
# la même justification écrite.
_STATELESS_EXECUTABLE_TASKS: frozenset[str] = frozenset({"sentiment"})


def _check_status_consistency() -> None:
    """Garantit que le statut déclaré et `MODULE_TRAINING_SPECS` ne divergent jamais."""

    for module_code, statuses in MODULE_TASK_STATUS.items():
        wired_tasks = set(MODULE_TRAINING_SPECS.get(module_code, {}))
        for task_code, status in statuses.items():
            if task_code in _STATELESS_EXECUTABLE_TASKS:
                continue
            is_wired = task_code in wired_tasks
            if status is CapabilityStatus.EXECUTABLE and not is_wired:
                raise AssertionError(
                    f"'{task_code}' is marked EXECUTABLE but has no MODULE_TRAINING_SPECS entry"
                )
            if status is not CapabilityStatus.EXECUTABLE and is_wired:
                raise AssertionError(
                    f"'{task_code}' is wired in MODULE_TRAINING_SPECS but not marked EXECUTABLE"
                )


_check_status_consistency()
