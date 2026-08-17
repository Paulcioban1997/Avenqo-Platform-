"""Catalogue des modèles Machine Learning : unique source de vérité, réutilisée par
l'AI Engine pour son domaine générique et par toute famille métier (ex : Forecasting
importe XGBoostModel/LightGBMModel directement d'ici, sans jamais les dupliquer).
"""

from shared.ai_engine.architectures.machine_learning.adaboost import AdaBoostModel
from shared.ai_engine.architectures.machine_learning.catboost import CatBoostModel
from shared.ai_engine.architectures.machine_learning.decision_tree import DecisionTreeModel
from shared.ai_engine.architectures.machine_learning.elastic_net import ElasticNetModel
from shared.ai_engine.architectures.machine_learning.extra_trees import ExtraTreesModel
from shared.ai_engine.architectures.machine_learning.gradient_boosting import (
    GradientBoostingModel,
)
from shared.ai_engine.architectures.machine_learning.hist_gradient_boosting import (
    HistGradientBoostingModel,
)
from shared.ai_engine.architectures.machine_learning.knn import KNNModel
from shared.ai_engine.architectures.machine_learning.lasso import LassoModel
from shared.ai_engine.architectures.machine_learning.lightgbm import LightGBMModel
from shared.ai_engine.architectures.machine_learning.linear_regression import (
    LinearRegressionModel,
)
from shared.ai_engine.architectures.machine_learning.logistic_regression import (
    LogisticRegressionModel,
)
from shared.ai_engine.architectures.machine_learning.random_forest import RandomForestModel
from shared.ai_engine.architectures.machine_learning.ridge import RidgeModel
from shared.ai_engine.architectures.machine_learning.svm import SVMModel
from shared.ai_engine.architectures.machine_learning.xgboost import XGBoostModel
from shared.ai_engine.core.model_candidate_registry import ModelCandidateRegistry


def build_machine_learning_registry() -> ModelCandidateRegistry:
    registry = ModelCandidateRegistry()
    registry.register("random_forest", RandomForestModel)
    registry.register("xgboost", XGBoostModel)
    registry.register("lightgbm", LightGBMModel)
    registry.register("catboost", CatBoostModel)
    registry.register("extra_trees", ExtraTreesModel)
    registry.register("hist_gradient_boosting", HistGradientBoostingModel)
    registry.register("logistic_regression", LogisticRegressionModel)
    registry.register("linear_regression", LinearRegressionModel)
    registry.register("ridge", RidgeModel)
    registry.register("lasso", LassoModel)
    registry.register("elastic_net", ElasticNetModel)
    registry.register("svm", SVMModel)
    registry.register("knn", KNNModel)
    registry.register("decision_tree", DecisionTreeModel)
    registry.register("adaboost", AdaBoostModel)
    registry.register("gradient_boosting", GradientBoostingModel)
    return registry
