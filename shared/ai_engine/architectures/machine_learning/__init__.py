"""Catégorie technique Machine Learning : modèles tabulaires classiques (unique source
de vérité, sans copie dans families/). Sert aussi de domaine d'exécution par défaut
de l'AIEngine, faute d'une famille métier plus spécifique.
"""

from shared.ai_engine.architectures.machine_learning.optimizer import (
	HyperparameterSearchResult,
	run_hyperparameter_search,
)
from shared.ai_engine.architectures.machine_learning.strategy import MachineLearningStrategy

__all__ = ["HyperparameterSearchResult", "MachineLearningStrategy", "run_hyperparameter_search"]
