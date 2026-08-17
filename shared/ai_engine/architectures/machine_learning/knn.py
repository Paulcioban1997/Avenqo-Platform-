"""Candidat k-plus-proches-voisins (sera implémenté avec sklearn.neighbors.KNeighborsClassifier/Regressor)."""

from shared.ai_engine.core.model_stub import UntrainedModel


class KNNModel(UntrainedModel):
    candidate_id = "knn"
